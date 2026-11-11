/* Count PyObject allocations without re-entering the Python allocator.
 *
 * The hooks are plain C. A ctypes callback cannot do this: the malloc hook
 * would allocate a Python frame and recurse until the stack overflows.
 */
#include <stddef.h>
#include <stdint.h>

static uint64_t alloc_count;

static void *orig_ctx;
static void *(*orig_malloc)(void *, size_t);
static void *(*orig_calloc)(void *, size_t, size_t);
static void *(*orig_realloc)(void *, void *, size_t);
static void (*orig_free)(void *, void *);

static void *hook_malloc(void *ctx, size_t size) {
    (void)ctx;
    alloc_count++;
    return orig_malloc(orig_ctx, size);
}

static void *hook_calloc(void *ctx, size_t nelem, size_t size) {
    (void)ctx;
    alloc_count++;
    return orig_calloc(orig_ctx, nelem, size);
}

static void *hook_realloc(void *ctx, void *ptr, size_t size) {
    (void)ctx;
    alloc_count++;
    return orig_realloc(orig_ctx, ptr, size);
}

static void hook_free(void *ctx, void *ptr) {
    (void)ctx;
    orig_free(orig_ctx, ptr);
}

void alloccount_install(void *ctx, void *malloc_fn, void *calloc_fn,
                        void *realloc_fn, void *free_fn,
                        void **out_malloc, void **out_calloc,
                        void **out_realloc, void **out_free) {
    orig_ctx = ctx;
    orig_malloc = (void *(*)(void *, size_t))malloc_fn;
    orig_calloc = (void *(*)(void *, size_t, size_t))calloc_fn;
    orig_realloc = (void *(*)(void *, void *, size_t))realloc_fn;
    orig_free = (void (*)(void *, void *))free_fn;
    alloc_count = 0;
    *out_malloc = (void *)hook_malloc;
    *out_calloc = (void *)hook_calloc;
    *out_realloc = (void *)hook_realloc;
    *out_free = (void *)hook_free;
}

uint64_t alloccount_read(void) {
    return alloc_count;
}

void alloccount_reset(void) {
    alloc_count = 0;
}
