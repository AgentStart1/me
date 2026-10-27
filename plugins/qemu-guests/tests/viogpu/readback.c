#define SDL_MAIN_HANDLED
#include "pipe/p_defines.h"
#include "virgl_hw.h"
#include "virglrenderer.h"
#include "vrend/vrend_iov.h"
#include <SDL2/SDL.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static SDL_Window *window;
static void *create(void *c, int idx, struct virgl_renderer_gl_ctx_param *p) {
  SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, p->major_ver);
  SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, p->minor_ver);
  SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK,
                      p->compat_ctx ? SDL_GL_CONTEXT_PROFILE_COMPATIBILITY
                                    : SDL_GL_CONTEXT_PROFILE_CORE);
  SDL_GL_SetAttribute(SDL_GL_SHARE_WITH_CURRENT_CONTEXT, p->shared);
  return SDL_GL_CreateContext(window);
}
static void destroy(void *c, void *g) { SDL_GL_DeleteContext(g); }
static int current(void *c, int idx, void *g) {
  return SDL_GL_MakeCurrent(window, g);
}
static void fence(void *c, uint32_t f) {}
#define CHECK(x)                                                               \
  do {                                                                         \
    int r = (x);                                                               \
    if (r) {                                                                   \
      fprintf(stderr, "%s => %d (%s)\n", #x, r, SDL_GetError());               \
      return 2;                                                                \
    }                                                                          \
  } while (0)
int main(void) {
  SDL_SetMainReady();
  CHECK(SDL_Init(SDL_INIT_VIDEO));
  window = SDL_CreateWindow("transfer regression", 0, 0, 32, 32,
                            SDL_WINDOW_OPENGL | SDL_WINDOW_HIDDEN);
  if (!window)
    return 2;
  struct virgl_renderer_callbacks cb = {.version = 1,
                                        .create_gl_context = create,
                                        .destroy_gl_context = destroy,
                                        .make_current = current,
                                        .write_fence = fence};
  CHECK(virgl_renderer_init(&cb, 0, &cb));
  unsigned formats[] = {VIRGL_FORMAT_Z24_UNORM_S8_UINT,
                        VIRGL_FORMAT_Z24X8_UNORM, VIRGL_FORMAT_R8G8B8A8_UNORM};
  int failed = 0, total = 0;
  for (unsigned fi = 0; fi < 3; fi++)
    for (unsigned mip = 0; mip < 2; mip++)
      for (unsigned padded = 0; padded < 2; padded++)
        for (unsigned split = 0; split < 2; split++) {
          struct virgl_renderer_resource_create_args a = {
              .handle = 1,
              .target = PIPE_TEXTURE_2D_ARRAY,
              .format = formats[fi],
              .bind =
                  fi == 2 ? PIPE_BIND_RENDER_TARGET : PIPE_BIND_DEPTH_STENCIL,
              .width = 8,
              .height = 8,
              .depth = 1,
              .array_size = 4,
              .last_level = 1};
          CHECK(virgl_renderer_resource_create(&a, 0, 0));
          unsigned w = 8 >> mip, h = 8 >> mip;
          uint32_t pixels[4 * 64];
          for (unsigned z = 0; z < 4; z++)
            for (unsigned y = 0; y < h; y++)
              for (unsigned x = 0; x < w; x++)
                pixels[z * w * h + y * w + x] = (fi == 1 ? 0 : 0x71000000) +
                                                z * 0x130123 + y * 0x1300 +
                                                x * 0x102;
          if (fi == 1) {
            const uint32_t boundary[] = {0, 1, 0xff, 0x100, 0xfffffe, 0xffffff};
            for (unsigned z = 0; z < 4; z++)
              for (unsigned y = 0; y < h; y++)
                for (unsigned x = 0; x < w; x++)
                  pixels[z * w * h + y * w + x] = boundary[(x + y + z) % 6];
          }
          uint32_t original[4 * 64];
          memcpy(original, pixels, w * h * 4 * 4);
          struct iovec src = {pixels, w * h * 4 * 4};
          struct virgl_box all = {0, 0, 0, w, h, 4};
          CHECK(virgl_renderer_transfer_write_iov(1, 0, mip, 0, 0, &all, 0,
                                                  &src, 1));
          unsigned char output[2048], expected[2048];
          memset(output, 0xcd, sizeof(output));
          memset(expected, 0xcd, sizeof(expected));
          struct virgl_box box = {1, 1, 1, w - 2, h - 2, 2};
          unsigned stride = padded ? 48 : w * 4,
                   layer = padded ? 512 : stride * h, offset = 17;
          for (unsigned z = 0; z < box.d; z++)
            for (unsigned y = 0; y < box.h; y++)
              memcpy(expected + offset + z * layer + y * stride,
                     &original[(z + 1) * w * h + (y + 1) * w + 1], box.w * 4);
          struct iovec dst[2] = {{output, split ? 73 : sizeof(output)},
                                 {output + 73, sizeof(output) - 73}};
          CHECK(virgl_renderer_transfer_read_iov(1, 0, mip, padded ? stride : 0,
                                                 padded ? layer : 0, &box,
                                                 offset, dst, split ? 2 : 1));
          int bad = memcmp(output, expected, sizeof(output)) != 0 ||
                    memcmp(original, pixels, w * h * 4 * 4) != 0;
          printf("format=%u mip=%u padded=%u split=%u %s\n", formats[fi], mip,
                 padded, split, bad ? "FAIL" : "PASS");
          failed += bad;
          total++;
          virgl_renderer_resource_unref(1);
        }
  virgl_renderer_cleanup(&cb);
  SDL_DestroyWindow(window);
  SDL_Quit();
  printf("RESULT %d/%d passed\n", total - failed, total);
  return failed ? 1 : 0;
}
