/* SPDX-License-Identifier: GPL-2.0-or-later */
#define SDL_MAIN_HANDLED
#include <SDL.h>
#include <stdio.h>
#include "gl-snapshot.h"

static int cases;

#define CHECK(condition) do { if (!(condition)) { \
    fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #condition); exit(1); \
} } while (0)

static void pixel(uint8_t *p, int x, int y, int seed)
{
    p[0] = (x * 19 + seed) & 255;
    p[1] = (y * 23 + seed) & 255;
    p[2] = (x + y * 7 + seed) & 255;
    p[3] = 255;
}

static GLuint texture(int w, int h, int seed)
{
    uint8_t data[13 * 7 * 4];
    GLuint result;
    for (int y = 0; y < h; y++) {
        for (int x = 0; x < w; x++) {
            pixel(data + (y * w + x) * 4, x, y, seed);
        }
    }
    glGenTextures(1, &result);
    glBindTexture(GL_TEXTURE_2D, result);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, w, h, 0, GL_RGBA,
                 GL_UNSIGNED_BYTE, data);
    return result;
}

static GLint value(GLenum name)
{
    GLint result;
    glGetIntegerv(name, &result);
    return result;
}

static void check_state(GLuint source, GLuint read, GLuint draw, GLuint pbo)
{
    CHECK(value(GL_READ_FRAMEBUFFER_BINDING) == (GLint)read);
    CHECK(value(GL_DRAW_FRAMEBUFFER_BINDING) == (GLint)draw);
    CHECK(value(GL_PIXEL_PACK_BUFFER_BINDING) == (GLint)pbo);
    CHECK(value(GL_PACK_ALIGNMENT) == 8);
    CHECK(value(GL_PACK_ROW_LENGTH) == 19);
    CHECK(value(GL_PACK_SKIP_ROWS) == 2);
    CHECK(value(GL_PACK_SKIP_PIXELS) == 3);
    CHECK(value(GL_READ_BUFFER) == GL_COLOR_ATTACHMENT0);
    glBindFramebuffer(GL_READ_FRAMEBUFFER, source);
    CHECK(value(GL_READ_BUFFER) == GL_COLOR_ATTACHMENT1);
    glBindFramebuffer(GL_READ_FRAMEBUFFER, read);
    CHECK(glGetError() == GL_NO_ERROR);
}

static void run_case(int bw, int bh, bool cropped, bool top,
                     bool padded, bool packed, int failure)
{
    GLuint tex = texture(bw, bh, cases + 11);
    GLuint other = texture(bw, bh, cases + 91);
    GLuint source, read, draw, empty, pbo = 0, multisample = 0, renderbuffer = 0;
    uint8_t storage[4096], expected[4];
    uint8_t *data = storage + 128;
    int x = cropped ? 2 : 0, y = cropped ? 1 : 0;
    int w = cropped ? 5 : bw, h = cropped ? 3 : bh;
    int stride = w * 4 + (padded ? 12 : 0);
    const char *reason = NULL;
    bool success;

    glGenFramebuffers(1, &source);
    glBindFramebuffer(GL_FRAMEBUFFER, source);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, tex, 0);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT1, GL_TEXTURE_2D, other, 0);
    glReadBuffer(GL_COLOR_ATTACHMENT1);
    glGenFramebuffers(1, &read);
    glBindFramebuffer(GL_FRAMEBUFFER, read);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, other, 0);
    glReadBuffer(GL_COLOR_ATTACHMENT0);
    glGenFramebuffers(1, &draw);
    glBindFramebuffer(GL_DRAW_FRAMEBUFFER, draw);
    glFramebufferTexture2D(GL_DRAW_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, other, 0);
    glGenFramebuffers(1, &empty);
    if (failure == 4) {
        glGenRenderbuffers(1, &renderbuffer);
        glBindRenderbuffer(GL_RENDERBUFFER, renderbuffer);
        glRenderbufferStorageMultisample(GL_RENDERBUFFER, 4, GL_RGBA8, bw, bh);
        glGenFramebuffers(1, &multisample);
        glBindFramebuffer(GL_READ_FRAMEBUFFER, multisample);
        glFramebufferRenderbuffer(GL_READ_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                                  GL_RENDERBUFFER, renderbuffer);
        CHECK(glCheckFramebufferStatus(GL_READ_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE);
        glBindFramebuffer(GL_READ_FRAMEBUFFER, read);
    }
    if (packed) {
        glGenBuffers(1, &pbo);
        glBindBuffer(GL_PIXEL_PACK_BUFFER, pbo);
        glBufferData(GL_PIXEL_PACK_BUFFER, 1024, NULL, GL_STREAM_READ);
    }
    glPixelStorei(GL_PACK_ALIGNMENT, 8);
    glPixelStorei(GL_PACK_ROW_LENGTH, 19);
    glPixelStorei(GL_PACK_SKIP_ROWS, 2);
    glPixelStorei(GL_PACK_SKIP_PIXELS, 3);
    memset(storage, 0xa5, sizeof(storage));
    CHECK(glGetError() == GL_NO_ERROR);

    if (failure == 2) {
        glEnable(0xffff); /* Existing errors must fail, never publish a stale image. */
    }
    success = qemu_gl_snapshot_read(failure == 1 ? empty :
                                   failure == 4 ? multisample : source, bh, x, y,
                                   w, h, failure == 3 ? w * 4 - 1 : stride,
                                   data, top, &reason);
    CHECK(success == (failure == 0));
    if (failure) {
        CHECK(reason != NULL);
        for (size_t i = 0; i < sizeof(storage); i++) {
            CHECK(storage[i] == 0xa5);
        }
    } else {
        for (int row = 0; row < h; row++) {
            int gy = top ? bh - 1 - y - row : y + row;
            for (int col = 0; col < w; col++) {
                pixel(expected, x + col, gy, cases + 11);
                CHECK(!memcmp(data + row * stride + col * 4, expected, 4));
            }
        }
        for (size_t i = 0; i < sizeof(storage); i++) {
            bool written = i >= 128 && i < 128 + (size_t)h * stride &&
                           (i - 128) % stride < (size_t)w * 4;
            if (!written) {
                CHECK(storage[i] == 0xa5);
            }
        }
    }
    check_state(source, read, draw, pbo);
    glBindBuffer(GL_PIXEL_PACK_BUFFER, 0);
    glDeleteBuffers(1, &pbo);
    glBindFramebuffer(GL_FRAMEBUFFER, 0);
    glDeleteFramebuffers(1, &source);
    glDeleteFramebuffers(1, &read);
    glDeleteFramebuffers(1, &draw);
    glDeleteFramebuffers(1, &empty);
    glDeleteFramebuffers(1, &multisample);
    glDeleteRenderbuffers(1, &renderbuffer);
    glDeleteTextures(1, &tex);
    glDeleteTextures(1, &other);
    cases++;
}

int main(int argc, char **argv)
{
    (void)argc;
    (void)argv;
    SDL_SetMainReady();
    CHECK(SDL_Init(SDL_INIT_VIDEO) == 0);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 3);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 3);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_CORE);
    SDL_Window *window = SDL_CreateWindow("snapshot regression", 0, 0, 64, 64,
                                         SDL_WINDOW_OPENGL | SDL_WINDOW_HIDDEN);
    CHECK(window != NULL);
    SDL_GLContext context = SDL_GL_CreateContext(window);
    CHECK(context != NULL);
    printf("Renderer: %s\n", glGetString(GL_RENDERER));
    for (int size = 0; size < 2; size++) {
        for (int crop = 0; crop < 2; crop++) {
            for (int top = 0; top < 2; top++) {
                for (int pad = 0; pad < 2; pad++) {
                    for (int pack = 0; pack < 2; pack++) {
                        run_case(size ? 13 : 9, size ? 5 : 7, crop, top, pad, pack, 0);
                    }
                }
            }
        }
    }
    for (int error = 1; error <= 4; error++) {
        run_case(9, 7, true, true, true, true, error);
        run_case(9, 7, true, true, true, true, 0);
    }
    printf("RESULT %d/%d passed\n", cases, cases);
    SDL_GL_DeleteContext(context);
    SDL_DestroyWindow(window);
    SDL_Quit();
    return 0;
}
