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
  window = SDL_CreateWindow("read failure regression", 0, 0, 32, 32,
                            SDL_WINDOW_OPENGL | SDL_WINDOW_HIDDEN);
  if (!window)
    return 2;
  struct virgl_renderer_callbacks cb = {.version = 1,
                                        .create_gl_context = create,
                                        .destroy_gl_context = destroy,
                                        .make_current = current,
                                        .write_fence = fence};
  CHECK(virgl_renderer_init(&cb, 0, &cb));
  typedef unsigned(__stdcall * get_error_fn)(void);
  typedef void(__stdcall * pixel_store_fn)(unsigned, int);
  typedef void(__stdcall * enable_fn)(unsigned);
  get_error_fn get_error = (get_error_fn)SDL_GL_GetProcAddress("glGetError");
  pixel_store_fn pixel_store =
      (pixel_store_fn)SDL_GL_GetProcAddress("glPixelStorei");
  enable_fn enable = (enable_fn)SDL_GL_GetProcAddress("glEnable");
  int failures = 0, tests = 0;
  for (int mode = 0; mode < 3; mode++) {
    struct virgl_renderer_resource_create_args a = {
        .handle = 1,
        .target = PIPE_TEXTURE_2D,
        .format = VIRGL_FORMAT_R8G8B8A8_UNORM,
        .bind = PIPE_BIND_RENDER_TARGET,
        .width = 8,
        .height = 8,
        .depth = 1,
        .array_size = 1,
        .nr_samples = mode == 0 ? 4 : 0};
    CHECK(virgl_renderer_resource_create(&a, 0, 0));
    uint32_t source[64];
    for (unsigned i = 0; i < 64; i++)
      source[i] = 0x71000000 + i * 0x010203;
    struct virgl_box box = {0, 0, 0, 8, 8, 1};
    struct iovec src = {source, sizeof(source)};
    if (mode)
      CHECK(virgl_renderer_transfer_write_iov(1, 0, 0, 0, 0, &box, 0, &src, 1));
    unsigned char output[sizeof(source)];
    memset(output, 0xcd, sizeof(output));
    struct iovec dst = {output, sizeof(output)};
    while (get_error()) {
    }
    if (mode == 1)
      pixel_store(0x0d03,
                  1); /* GL_PACK_SKIP_ROWS: force a too-small GL read buffer. */
    if (mode == 2)
      enable(0xdead); /* Pending driver error at the operation boundary. */
    int rc = virgl_renderer_transfer_read_iov(1, 0, 0, 0, 0, &box, 0, &dst, 1);
    unsigned changed = 0;
    for (unsigned i = 0; i < sizeof(output); i++)
      if (output[i] != 0xcd)
        changed++;
    int pass = rc != 0 && changed == 0;
    printf("failure mode=%d rc=%d changed=%u %s\n", mode, rc, changed,
           pass ? "PASS" : "FAIL");
    failures += !pass;
    tests++;
    pixel_store(0x0d03, 0);
    while (get_error()) {
    }
    if (mode) {
      memset(output, 0xcd, sizeof(output));
      rc = virgl_renderer_transfer_read_iov(1, 0, 0, 0, 0, &box, 0, &dst, 1);
      pass = rc == 0 && memcmp(output, source, sizeof(output)) == 0;
      printf("recovery mode=%d %s\n", mode, pass ? "PASS" : "FAIL");
      failures += !pass;
      tests++;
    }
    virgl_renderer_resource_unref(1);
  }
  virgl_renderer_cleanup(&cb);
  SDL_DestroyWindow(window);
  SDL_Quit();
  printf("RESULT %d/%d passed\n", tests - failures, tests);
  return failures ? 1 : 0;
}
