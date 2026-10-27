#define COBJMACROS
#include <d3d11.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <windows.h>
#define SUBS 8
static FILE *logfile;
static uint32_t expected[SUBS][64];
static int cleared[SUBS];
#define HR(x)                                                                  \
  do {                                                                         \
    HRESULT hr = (x);                                                          \
    if (FAILED(hr)) {                                                          \
      fprintf(logfile, "FAIL %s hr=%08lx\n", #x, (unsigned long)hr);           \
      return 2;                                                                \
    }                                                                          \
  } while (0)
static uint32_t initial(int sub, int x, int y) {
  return ((uint32_t)(0x51 + sub * 13 + x + y) << 24) |
         ((0x123456u + sub * 0x113355u + x * 0x10203u + y * 0x30405u) &
          0xffffffu);
}
/* Verify every mip and layer after each operation, including untouched regions.
 */
static int verify(ID3D11DeviceContext *ctx, ID3D11Texture2D *texture,
                  ID3D11Texture2D *stage, const char *label) {
  ID3D11DeviceContext_CopyResource(ctx, (ID3D11Resource *)stage,
                                   (ID3D11Resource *)texture);
  int bad = 0;
  for (int sub = 0; sub < SUBS; sub++) {
    D3D11_MAPPED_SUBRESOURCE m;
    HR(ID3D11DeviceContext_Map(ctx, (ID3D11Resource *)stage, sub,
                               D3D11_MAP_READ, 0, &m));
    int width = 8 >> (sub % 2), height = 6 >> (sub % 2);
    for (int y = 0; y < height; y++)
      for (int x = 0; x < width; x++) {
        uint32_t actual =
                     *(uint32_t *)((char *)m.pData + y * m.RowPitch + x * 4),
                 want = expected[sub][y * 8 + x];
        int delta = (int)(actual & 0xffffff) - (int)(want & 0xffffff);
        if ((actual >> 24) != (want >> 24) ||
            (cleared[sub] ? delta < -1 || delta > 1 : delta != 0)) {
          if (!bad)
            fprintf(logfile,
                    "%s mismatch sub=%d xy=%d,%d got=%08x expected=%08x\n",
                    label, sub, x, y, actual, want);
          bad++;
        }
      }
    ID3D11DeviceContext_Unmap(ctx, (ID3D11Resource *)stage, sub);
  }
  fprintf(logfile, "%s %s mismatches=%d\n", label, bad ? "FAIL" : "PASS", bad);
  fflush(logfile);
  return bad ? 1 : 0;
}
int main(int argc, char **argv) {
  if (argc < 2)
    return 2;
  logfile = fopen(argv[1], "w");
  if (!logfile)
    return 2;
  ID3D11Device *device = 0;
  ID3D11DeviceContext *ctx = 0;
  D3D_FEATURE_LEVEL level,
      levels[] = {D3D_FEATURE_LEVEL_11_0, D3D_FEATURE_LEVEL_10_1,
                  D3D_FEATURE_LEVEL_10_0};
  int warp = argc > 2 && strcmp(argv[2], "warp") == 0,
      mutate = argc > 3 && strcmp(argv[3], "mutate") == 0;
  HR(D3D11CreateDevice(
      0, warp ? D3D_DRIVER_TYPE_WARP : D3D_DRIVER_TYPE_HARDWARE, 0, 0, levels,
      3, D3D11_SDK_VERSION, &device, &level, &ctx));
  fprintf(logfile, "feature=%x mutation=%d\n", level, mutate);
  D3D11_TEXTURE2D_DESC desc = {0};
  desc.Width = 8;
  desc.Height = 6;
  desc.MipLevels = 2;
  desc.ArraySize = 4;
  desc.Format = DXGI_FORMAT_R24G8_TYPELESS;
  desc.SampleDesc.Count = 1;
  desc.BindFlags = D3D11_BIND_DEPTH_STENCIL | D3D11_BIND_SHADER_RESOURCE;
  uint32_t data[SUBS][96];
  D3D11_SUBRESOURCE_DATA init[SUBS] = {0};
  for (int sub = 0; sub < SUBS; sub++) {
    int width = 8 >> (sub % 2), height = 6 >> (sub % 2);
    for (int y = 0; y < height; y++)
      for (int x = 0; x < width; x++)
        data[sub][y * 16 + x] = expected[sub][y * 8 + x] = initial(sub, x, y);
    init[sub].pSysMem = data[sub];
    init[sub].SysMemPitch = 64;
    init[sub].SysMemSlicePitch = 64 * height;
  }
  ID3D11Texture2D *texture = 0, *stage = 0;
  HR(ID3D11Device_CreateTexture2D(device, &desc, init, &texture));
  desc.BindFlags = 0;
  desc.Usage = D3D11_USAGE_STAGING;
  desc.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
  HR(ID3D11Device_CreateTexture2D(device, &desc, 0, &stage));
  int failed = verify(ctx, texture, stage, "initial upload");
  /* Distinct values make wrong-layer, wrong-mip and whole-resource clears
   * visible. */
  for (int step = 0; step < 11; step++) {
    unsigned mip = step < 8 ? step % 2 : 1, first = step < 8 ? step / 2 : 1,
             count = step < 8 ? 1 : 2;
    unsigned flags = step == 9    ? D3D11_CLEAR_DEPTH
                     : step == 10 ? D3D11_CLEAR_STENCIL
                                  : D3D11_CLEAR_DEPTH | D3D11_CLEAR_STENCIL;
    float depth = (step + 1) / 16.0f;
    unsigned stencil = 0xa0 + step;
    D3D11_DEPTH_STENCIL_VIEW_DESC view = {0};
    view.Format = DXGI_FORMAT_D24_UNORM_S8_UINT;
    view.ViewDimension = D3D11_DSV_DIMENSION_TEXTURE2DARRAY;
    view.Texture2DArray.MipSlice = mip;
    view.Texture2DArray.FirstArraySlice = first;
    view.Texture2DArray.ArraySize = count;
    /* Negative control intentionally expands only the actual clear range. */
    if (mutate && step == 0) {
      view.Texture2DArray.FirstArraySlice = 0;
      view.Texture2DArray.ArraySize = 4;
    }
    ID3D11DepthStencilView *dsv = 0;
    HR(ID3D11Device_CreateDepthStencilView(device, (ID3D11Resource *)texture,
                                           &view, &dsv));
    ID3D11DeviceContext_ClearDepthStencilView(ctx, dsv, flags, depth, stencil);
    ID3D11DepthStencilView_Release(dsv);
    for (unsigned layer = first; layer < first + count; layer++) {
      unsigned sub = layer * 2 + mip;
      int width = 8 >> mip, height = 6 >> mip;
      for (int y = 0; y < height; y++)
        for (int x = 0; x < width; x++) {
          uint32_t *v = &expected[sub][y * 8 + x];
          if (flags & D3D11_CLEAR_DEPTH)
            *v = (*v & 0xff000000) |
                 ((uint32_t)(depth * 16777215.0f + 0.5f) & 0xffffff);
          if (flags & D3D11_CLEAR_STENCIL)
            *v = (*v & 0xffffff) | (stencil << 24);
        }
      if (flags & D3D11_CLEAR_DEPTH)
        cleared[sub] = 1;
    }
    char label[96];
    snprintf(label, sizeof(label),
             "clear step=%d mip=%u layers=%u..%u flags=%u", step, mip, first,
             first + count - 1, flags);
    int result = verify(ctx, texture, stage, label);
    failed |= result;
    if (failed)
      break;
  }
  fprintf(logfile, "RESULT %s\n", failed ? "FAIL" : "PASS");
  ID3D11Texture2D_Release(stage);
  ID3D11Texture2D_Release(texture);
  ID3D11DeviceContext_Release(ctx);
  ID3D11Device_Release(device);
  fclose(logfile);
  return failed ? 1 : 0;
}
