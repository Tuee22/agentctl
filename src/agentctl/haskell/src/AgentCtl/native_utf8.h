/* Copyright (c) 2026 agentctl contributors. */
#ifndef AGENTCTL_NATIVE_UTF8_H
#define AGENTCTL_NATIVE_UTF8_H
#include <errno.h>
#include <stdlib.h>
#include <wchar.h>
#include <windows.h>
static wchar_t *wide(const char *text) {
  int length = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, text, -1, NULL, 0);
  if (!length) { errno = EINVAL; return NULL; }
  wchar_t *result = malloc((size_t)length * sizeof(wchar_t));
  if (!result) { errno = ENOMEM; return NULL; }
  if (!MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, text, -1, result, length)) {
    free(result); errno = EINVAL; return NULL;
  }
  return result;
}

#endif
