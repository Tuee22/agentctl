/* Copyright (c) 2026 agentctl contributors. */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif
#include <errno.h>
#include <stdlib.h>

#ifdef _WIN32
#include <windows.h>
#include <aclapi.h>
#include <sddl.h>
#include "../src/AgentCtl/native_utf8.h"

typedef BOOL (WINAPI *ConvertFn)(LPCWSTR, DWORD, PSECURITY_DESCRIPTOR *, PULONG);
typedef BOOL (WINAPI *DaclFn)(PSECURITY_DESCRIPTOR, LPBOOL, PACL *, LPBOOL);
typedef DWORD (WINAPI *NamedFn)(LPWSTR, SE_OBJECT_TYPE, SECURITY_INFORMATION, PSID, PSID, PACL, PACL);

#define LOOKUP(variable, type, name) \
  union { FARPROC raw; type call; } variable = { .raw = GetProcAddress(library, name) }

/* Called only for the fresh directory a native test created under its temp root. */
int agentctl_test_public_state(const char *path) {
  wchar_t *name = wide(path);
  if (!name) return errno;
  int error = 0;
  HMODULE library = NULL;
  PSECURITY_DESCRIPTOR descriptor = NULL;
  DWORD attributes = GetFileAttributesW(name);
  if (attributes == INVALID_FILE_ATTRIBUTES) { error = (int)GetLastError(); goto finish; }
  if (!(attributes & FILE_ATTRIBUTE_DIRECTORY) || (attributes & FILE_ATTRIBUTE_REPARSE_POINT)) {
    error = ERROR_ACCESS_DENIED; goto finish;
  }
  library = LoadLibraryExW(L"advapi32.dll", NULL, LOAD_LIBRARY_SEARCH_SYSTEM32);
  if (!library) { error = (int)GetLastError(); goto finish; }
  LOOKUP(convert, ConvertFn, "ConvertStringSecurityDescriptorToSecurityDescriptorW");
  LOOKUP(dacl, DaclFn, "GetSecurityDescriptorDacl");
  LOOKUP(named, NamedFn, "SetNamedSecurityInfoW");
  if (!convert.raw || !dacl.raw || !named.raw) { error = ERROR_PROC_NOT_FOUND; goto finish; }
  if (!convert.call(L"D:(A;OICI;FA;;;WD)", SDDL_REVISION_1, &descriptor, NULL)) {
    error = (int)GetLastError(); goto finish;
  }
  BOOL present = FALSE, defaulted = FALSE;
  PACL acl = NULL;
  if (!dacl.call(descriptor, &present, &acl, &defaulted)) { error = (int)GetLastError(); goto finish; }
  if (!present || !acl) { error = ERROR_ACCESS_DENIED; goto finish; }
  error = (int)named.call(name, SE_FILE_OBJECT,
    DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION, NULL, NULL, acl, NULL);
finish:
  if (descriptor) LocalFree(descriptor);
  if (library) FreeLibrary(library);
  free(name);
  return error;
}
#else
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

int agentctl_test_public_state(const char *path) {
  int handle = open(path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  if (handle < 0) return errno;
  struct stat info;
  int error = 0;
  if (fstat(handle, &info)) error = errno;
  else if (!S_ISDIR(info.st_mode) || info.st_uid != geteuid()) error = EACCES;
  else if (fchmod(handle, 0755)) error = errno;
  if (close(handle) && !error) error = errno;
  return error;
}
#endif
