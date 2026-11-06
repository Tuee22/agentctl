/* Copyright (c) 2026 agentctl contributors. */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#ifdef __APPLE__
#define _DARWIN_C_SOURCE
#endif
#endif
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define AGENTCTL_SPEC_LIMIT (32U * 1024U * 1024U)

static long long lock_owner(const char *bytes, size_t length) {
  if (!length || length >= 64) return 0;
  char text[64];
  memcpy(text, bytes, length);
  text[length] = '\0';
  char *end = NULL;
  errno = 0;
  long long owner = strtoll(text, &end, 10);
  return !errno && owner > 0 && end && *end == '\n' && end[1] == '\0' ? owner : 0;
}

static int private_name(const char *name) {
  return *name && strcmp(name, ".") && strcmp(name, "..") && !strchr(name, '/') && !strchr(name, '\\');
}

#ifdef _WIN32
#include <windows.h>
#include <aclapi.h>

#include "native_utf8.h"

typedef DWORD (WINAPI *SecurityInfoFn)(HANDLE, SE_OBJECT_TYPE, SECURITY_INFORMATION, PSID *, PSID *, PACL *, PACL *, PSECURITY_DESCRIPTOR *);
typedef BOOL (WINAPI *OpenTokenFn)(HANDLE, DWORD, PHANDLE);
typedef BOOL (WINAPI *TokenInfoFn)(HANDLE, TOKEN_INFORMATION_CLASS, LPVOID, DWORD, PDWORD);
typedef BOOL (WINAPI *EqualSidFn)(PSID, PSID);
typedef BOOL (WINAPI *GetAceFn)(PACL, DWORD, LPVOID *);
typedef BOOL (WINAPI *WellKnownFn)(WELL_KNOWN_SID_TYPE, PSID, PSID, DWORD *);
typedef DWORD (WINAPI *SetEntriesFn)(ULONG, PEXPLICIT_ACCESS_W, PACL, PACL *);
typedef DWORD (WINAPI *SetSecurityFn)(HANDLE, SE_OBJECT_TYPE, SECURITY_INFORMATION, PSID, PSID, PACL, PACL);

#define LOOKUP(variable, type, name) \
  union { FARPROC raw; type call; } variable = { .raw = GetProcAddress(library, name) }

static int access_facts(HANDLE handle, int directory, unsigned int *facts) {
  HMODULE library = LoadLibraryExW(L"advapi32.dll", NULL, LOAD_LIBRARY_SEARCH_SYSTEM32);
  if (!library) return (int)GetLastError();
  LOOKUP(security, SecurityInfoFn, "GetSecurityInfo");
  LOOKUP(open_token, OpenTokenFn, "OpenProcessToken");
  LOOKUP(token_info, TokenInfoFn, "GetTokenInformation");
  LOOKUP(equal_sid, EqualSidFn, "EqualSid");
  LOOKUP(get_ace, GetAceFn, "GetAce");
  LOOKUP(well_known, WellKnownFn, "CreateWellKnownSid");
  int error = ERROR_PROC_NOT_FOUND;
  HANDLE token = NULL;
  TOKEN_USER *user = NULL;
  PSECURITY_DESCRIPTOR descriptor = NULL;
  if (!security.raw || !open_token.raw || !token_info.raw || !equal_sid.raw || !get_ace.raw || !well_known.raw) goto finish;
  BY_HANDLE_FILE_INFORMATION info;
  if (!GetFileInformationByHandle(handle, &info)) { error = (int)GetLastError(); goto finish; }
  facts[0] = GetFileType(handle) == FILE_TYPE_DISK && !(info.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT)
    && (!!(info.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) == directory);
  if (!open_token.call(GetCurrentProcess(), TOKEN_QUERY, &token)) { error = (int)GetLastError(); goto finish; }
  DWORD needed = 0;
  token_info.call(token, TokenUser, NULL, 0, &needed);
  if (!needed) { error = (int)GetLastError(); goto finish; }
  user = malloc(needed);
  if (!user) { error = ERROR_NOT_ENOUGH_MEMORY; goto finish; }
  if (!token_info.call(token, TokenUser, user, needed, &needed)) { error = (int)GetLastError(); goto finish; }
  PSID owner = NULL;
  PACL acl = NULL;
  error = (int)security.call(handle, SE_FILE_OBJECT, OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION,
                            &owner, NULL, &acl, NULL, &descriptor);
  if (error) goto finish;
  facts[1] = owner && equal_sid.call(owner, user->User.Sid);
  union { SID alignment; unsigned char bytes[SECURITY_MAX_SID_SIZE]; } system_sid, admin_sid;
  DWORD system_size = sizeof(system_sid.bytes), admin_size = sizeof(admin_sid.bytes);
  if (!well_known.call(WinLocalSystemSid, NULL, system_sid.bytes, &system_size)
      || !well_known.call(WinBuiltinAdministratorsSid, NULL, admin_sid.bytes, &admin_size)) {
    error = (int)GetLastError(); goto finish;
  }
  int private_acl = acl != NULL;
  for (DWORD index = 0; private_acl && index < acl->AceCount; ++index) {
    void *entry = NULL;
    if (!get_ace.call(acl, index, &entry)) { error = (int)GetLastError(); goto finish; }
    ACE_HEADER *header = entry;
    if (header->AceFlags & INHERIT_ONLY_ACE) continue;
    if (header->AceType == ACCESS_DENIED_ACE_TYPE) continue;
    if (header->AceType != ACCESS_ALLOWED_ACE_TYPE) { private_acl = 0; break; }
    ACCESS_ALLOWED_ACE *ace = (ACCESS_ALLOWED_ACE *)header;
    PSID sid = (PSID)&ace->SidStart;
    if (ace->Mask && !equal_sid.call(sid, user->User.Sid)
        && !equal_sid.call(sid, system_sid.bytes) && !equal_sid.call(sid, admin_sid.bytes)) private_acl = 0;
  }
  facts[2] = private_acl ? (directory ? 0700U : 0600U) : 0777U;
finish:
  if (descriptor) LocalFree(descriptor);
  free(user);
  if (token) CloseHandle(token);
  FreeLibrary(library);
  return error;
}

int agentctl_private_directory(const char *path) {
  wchar_t *name = wide(path);
  if (!name) return errno;
  int error = 0;
  if (!CreateDirectoryW(name, NULL) && GetLastError() != ERROR_ALREADY_EXISTS) {
    error = (int)GetLastError();
  } else {
    HANDLE handle = CreateFileW(name, READ_CONTROL | FILE_READ_ATTRIBUTES, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL,
                               OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, NULL);
    if (handle == INVALID_HANDLE_VALUE) error = (int)GetLastError();
    else {
      unsigned int facts[3] = {0};
      error = access_facts(handle, 1, facts);
      if (!error && (!facts[0] || !facts[1] || facts[2] != 0700U)) error = ERROR_ACCESS_DENIED;
      CloseHandle(handle);
    }
  }
  free(name);
  return error;
}

int agentctl_state_directory(const char *path) {
  wchar_t *name = wide(path);
  if (!name) return errno;
  int error = 0;
  HANDLE handle = INVALID_HANDLE_VALUE;
  HMODULE library = NULL;
  PSECURITY_DESCRIPTOR descriptor = NULL;
  PACL private_acl = NULL;
  if (!CreateDirectoryW(name, NULL) && GetLastError() != ERROR_ALREADY_EXISTS) {
    error = (int)GetLastError(); goto finish;
  }
  handle = CreateFileW(name, READ_CONTROL | FILE_READ_ATTRIBUTES,
                       FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING,
                       FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, NULL);
  if (handle == INVALID_HANDLE_VALUE) { error = (int)GetLastError(); goto finish; }
  unsigned int facts[3] = {0};
  error = access_facts(handle, 1, facts);
  if (error) goto finish;
  if (!facts[0] || !facts[1]) { error = ERROR_ACCESS_DENIED; goto finish; }
  if (facts[2] == 0700U) goto finish;
  CloseHandle(handle);
  /* An exclusive root handle prevents ACL propagation to existing children. */
  handle = CreateFileW(name, READ_CONTROL | WRITE_DAC | FILE_READ_ATTRIBUTES,
                       0, NULL, OPEN_EXISTING,
                       FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, NULL);
  if (handle == INVALID_HANDLE_VALUE) { error = (int)GetLastError(); goto finish; }
  error = access_facts(handle, 1, facts);
  if (error) goto finish;
  if (!facts[0] || !facts[1]) { error = ERROR_ACCESS_DENIED; goto finish; }
  if (facts[2] == 0700U) goto finish;
  library = LoadLibraryExW(L"advapi32.dll", NULL, LOAD_LIBRARY_SEARCH_SYSTEM32);
  if (!library) { error = (int)GetLastError(); goto finish; }
  LOOKUP(security, SecurityInfoFn, "GetSecurityInfo");
  LOOKUP(entries, SetEntriesFn, "SetEntriesInAclW");
  LOOKUP(set_security, SetSecurityFn, "SetSecurityInfo");
  if (!security.raw || !entries.raw || !set_security.raw) { error = ERROR_PROC_NOT_FOUND; goto finish; }
  PSID owner = NULL;
  error = (int)security.call(handle, SE_FILE_OBJECT, OWNER_SECURITY_INFORMATION,
                            &owner, NULL, NULL, NULL, &descriptor);
  if (error) goto finish;
  if (!owner) { error = ERROR_ACCESS_DENIED; goto finish; }
  EXPLICIT_ACCESSW entry;
  memset(&entry, 0, sizeof(entry));
  entry.grfAccessPermissions = FILE_ALL_ACCESS;
  entry.grfAccessMode = SET_ACCESS;
  entry.grfInheritance = SUB_CONTAINERS_AND_OBJECTS_INHERIT;
  entry.Trustee.TrusteeForm = TRUSTEE_IS_SID;
  entry.Trustee.TrusteeType = TRUSTEE_IS_USER;
  entry.Trustee.ptstrName = (LPWSTR)owner;
  error = (int)entries.call(1, &entry, NULL, &private_acl);
  if (error) goto finish;
  error = (int)set_security.call(handle, SE_FILE_OBJECT,
    DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION, NULL, NULL, private_acl, NULL);
  if (error) goto finish;
  error = access_facts(handle, 1, facts);
  if (!error && (!facts[0] || !facts[1] || facts[2] != 0700U)) error = ERROR_ACCESS_DENIED;
finish:
  if (private_acl) LocalFree(private_acl);
  if (descriptor) LocalFree(descriptor);
  if (library) FreeLibrary(library);
  if (handle != INVALID_HANDLE_VALUE) CloseHandle(handle);
  free(name);
  return error;
}

typedef struct { HANDLE file; HANDLE parent; } AgentctlLock;

void agentctl_lock_release(void *pointer) {
  AgentctlLock *lock = pointer;
  OVERLAPPED offset = {0};
  UnlockFileEx(lock->file, 0, 1, 0, &offset);
  CloseHandle(lock->file);
  CloseHandle(lock->parent);
  free(lock);
}

void *agentctl_lock_take(const char *directory, const char *name, long long *owner, int *error) {
  HANDLE parent = INVALID_HANDLE_VALUE, file = INVALID_HANDLE_VALUE;
  wchar_t *dir = NULL, *base = NULL, *path = NULL;
  AgentctlLock *lock = NULL;
  *owner = 0;
  *error = 0;
  if (!private_name(name)) { *error = ERROR_INVALID_NAME; goto finish; }
  dir = wide(directory);
  base = wide(name);
  if (!dir || !base) { *error = errno; goto finish; }
  size_t count = wcslen(dir) + wcslen(base) + 2;
  path = malloc(count * sizeof(wchar_t));
  if (!path) { *error = ENOMEM; goto finish; }
  wcscpy(path, dir);
  wcscat(path, L"\\");
  wcscat(path, base);
  parent = CreateFileW(dir, READ_CONTROL | FILE_READ_ATTRIBUTES, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL,
                       OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, NULL);
  if (parent == INVALID_HANDLE_VALUE) { *error = (int)GetLastError(); goto finish; }
  unsigned int facts[3] = {0};
  *error = access_facts(parent, 1, facts);
  if (*error) goto finish;
  if (!facts[0] || !facts[1] || facts[2] != 0700U) { *error = ERROR_ACCESS_DENIED; goto finish; }
  file = CreateFileW(path, GENERIC_READ | GENERIC_WRITE | READ_CONTROL, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL,
                     OPEN_ALWAYS, FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS, NULL);
  if (file == INVALID_HANDLE_VALUE) { *error = (int)GetLastError(); goto finish; }
  *error = access_facts(file, 0, facts);
  if (*error) goto finish;
  BY_HANDLE_FILE_INFORMATION info;
  if (!GetFileInformationByHandle(file, &info)) { *error = (int)GetLastError(); goto finish; }
  if (!facts[0] || !facts[1] || facts[2] != 0600U || info.nNumberOfLinks != 1) { *error = ERROR_ACCESS_DENIED; goto finish; }
  OVERLAPPED offset = {0};
  if (!LockFileEx(file, LOCKFILE_EXCLUSIVE_LOCK | LOCKFILE_FAIL_IMMEDIATELY, 0, 1, 0, &offset)) {
    *error = (int)GetLastError();
    if (*error == ERROR_LOCK_VIOLATION) {
      LARGE_INTEGER position;
      position.QuadPart = 1;
      char bytes[63];
      DWORD length = 0;
      if (SetFilePointerEx(file, position, NULL, FILE_BEGIN) && ReadFile(file, bytes, sizeof(bytes), &length, NULL))
        *owner = lock_owner(bytes, length);
      *error = -1;
    }
    goto finish;
  }
  char bytes[64];
  int length = snprintf(bytes, sizeof(bytes), "\n%lld\n", (long long)GetCurrentProcessId());
  DWORD written = 0;
  if (length <= 0 || (size_t)length >= sizeof(bytes)) { *error = ERROR_INVALID_DATA; goto finish; }
  if (!WriteFile(file, bytes, (DWORD)length, &written, NULL) || written != (DWORD)length || !SetEndOfFile(file)) {
    *error = (int)GetLastError();
    if (!*error) *error = ERROR_WRITE_FAULT;
    goto finish;
  }
  lock = malloc(sizeof(AgentctlLock));
  if (!lock) { *error = ENOMEM; goto finish; }
  lock->file = file;
  lock->parent = parent;
  file = parent = INVALID_HANDLE_VALUE;
finish:
  if (file != INVALID_HANDLE_VALUE) CloseHandle(file);
  if (parent != INVALID_HANDLE_VALUE) CloseHandle(parent);
  free(path); free(base); free(dir);
  return lock;
}

int agentctl_log_append(const char *directory, const char *name, const unsigned char *bytes, size_t length) {
  HANDLE parent = INVALID_HANDLE_VALUE, file = INVALID_HANDLE_VALUE;
  wchar_t *dir = NULL, *base = NULL, *path = NULL;
  int error = 0;
  if (!private_name(name)) return ERROR_INVALID_NAME;
  dir = wide(directory);
  base = wide(name);
  if (!dir || !base) { error = errno; goto finish; }
  size_t count = wcslen(dir) + wcslen(base) + 2;
  path = malloc(count * sizeof(wchar_t));
  if (!path) { error = ENOMEM; goto finish; }
  wcscpy(path, dir);
  wcscat(path, L"\\");
  wcscat(path, base);
  parent = CreateFileW(dir, READ_CONTROL | FILE_READ_ATTRIBUTES, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL,
                       OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, NULL);
  if (parent == INVALID_HANDLE_VALUE) { error = (int)GetLastError(); goto finish; }
  unsigned int facts[3] = {0};
  error = access_facts(parent, 1, facts);
  if (error) goto finish;
  if (!facts[0] || !facts[1] || facts[2] != 0700U) { error = ERROR_ACCESS_DENIED; goto finish; }
  file = CreateFileW(path, GENERIC_WRITE | FILE_READ_ATTRIBUTES | READ_CONTROL, FILE_SHARE_READ | FILE_SHARE_WRITE,
                     NULL, OPEN_ALWAYS, FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS, NULL);
  if (file == INVALID_HANDLE_VALUE) { error = (int)GetLastError(); goto finish; }
  error = access_facts(file, 0, facts);
  if (error) goto finish;
  BY_HANDLE_FILE_INFORMATION info;
  if (!GetFileInformationByHandle(file, &info)) { error = (int)GetLastError(); goto finish; }
  if (!facts[0] || !facts[1] || facts[2] != 0600U || info.nNumberOfLinks != 1) { error = ERROR_ACCESS_DENIED; goto finish; }
  size_t written = 0;
  while (written < length) {
    DWORD wanted = (DWORD)(length - written > 65536 ? 65536 : length - written);
    DWORD sent = 0;
    OVERLAPPED end = {0};
    end.Offset = MAXDWORD;
    end.OffsetHigh = MAXDWORD;
    if (!WriteFile(file, bytes + written, wanted, &sent, &end) || !sent) {
      error = (int)GetLastError();
      if (!error) error = ERROR_WRITE_FAULT;
      goto finish;
    }
    written += sent;
  }
  if (!FlushFileBuffers(file)) error = (int)GetLastError();
finish:
  if (file != INVALID_HANDLE_VALUE && !CloseHandle(file) && !error) error = (int)GetLastError();
  if (parent != INVALID_HANDLE_VALUE) CloseHandle(parent);
  free(path); free(base); free(dir);
  return error;
}

static unsigned char *snapshot_file(const char *directory, const char *name, unsigned int *facts, size_t *length, int *error, int shared) {
  unsigned char *bytes = NULL;
  HANDLE parent = INVALID_HANDLE_VALUE, file = INVALID_HANDLE_VALUE;
  wchar_t *dir = wide(directory), *base = wide(name), *path = NULL;
  *length = 0;
  *error = 0;
  if (!dir || !base) { *error = errno; goto finish; }
  size_t count = wcslen(dir) + wcslen(base) + 2;
  path = malloc(count * sizeof(wchar_t));
  if (!path) { *error = ENOMEM; goto finish; }
  wcscpy(path, dir);
  wcscat(path, L"\\");
  wcscat(path, base);
  parent = CreateFileW(dir, READ_CONTROL | FILE_READ_ATTRIBUTES, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL,
                       OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, NULL);
  if (parent == INVALID_HANDLE_VALUE) { *error = (int)GetLastError(); goto finish; }
  *error = access_facts(parent, 1, facts + 3);
  if (*error) goto finish;
  file = CreateFileW(path, GENERIC_READ | READ_CONTROL, FILE_SHARE_READ | (shared ? FILE_SHARE_WRITE : 0), NULL, OPEN_EXISTING,
                     FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS, NULL);
  if (file == INVALID_HANDLE_VALUE) { *error = (int)GetLastError(); goto finish; }
  *error = access_facts(file, 0, facts);
  if (*error) goto finish;
  LARGE_INTEGER size;
  size.QuadPart = 0;
  if (facts[0] && !GetFileSizeEx(file, &size)) { *error = (int)GetLastError(); goto finish; }
  if (size.QuadPart < 0 || (uint64_t)size.QuadPart > (shared ? SIZE_MAX - 1 : AGENTCTL_SPEC_LIMIT)) { *error = EFBIG; goto finish; }
  bytes = malloc((size_t)size.QuadPart + 1);
  if (!bytes) { *error = ENOMEM; goto finish; }
  while (*length < (size_t)size.QuadPart) {
    DWORD wanted = (DWORD)(((size_t)size.QuadPart - *length) > 65536 ? 65536 : ((size_t)size.QuadPart - *length));
    DWORD received = 0;
    if (!ReadFile(file, bytes + *length, wanted, &received, NULL) || !received) {
      *error = ERROR_READ_FAULT; free(bytes); bytes = NULL; goto finish;
    }
    *length += received;
  }
finish:
  if (file != INVALID_HANDLE_VALUE) CloseHandle(file);
  if (parent != INVALID_HANDLE_VALUE) CloseHandle(parent);
  free(path); free(base); free(dir);
  return bytes;
}


#else
#include <fcntl.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>

int agentctl_private_directory(const char *path) {
  if (mkdir(path, 0700) && errno != EEXIST) return errno;
  struct stat info;
  if (lstat(path, &info)) return errno;
  if (!S_ISDIR(info.st_mode) || info.st_uid != geteuid() || (info.st_mode & 07777U & ~0700U)) return EACCES;
  return 0;
}

int agentctl_state_directory(const char *path) {
  if (mkdir(path, 0700) && errno != EEXIST) return errno;
  int handle = open(path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  if (handle < 0) return errno;
  struct stat info;
  int error = 0;
  if (fstat(handle, &info)) error = errno;
  else if (!S_ISDIR(info.st_mode) || info.st_uid != geteuid()) error = EACCES;
  else if (fchmod(handle, 0700)) error = errno;
  if (close(handle) && !error) error = errno;
  return error;
}

static void access_facts(const struct stat *info, int directory, unsigned int *facts) {
  facts[0] = directory ? S_ISDIR(info->st_mode) : S_ISREG(info->st_mode);
  facts[1] = info->st_uid == geteuid();
  facts[2] = info->st_mode & 07777U;
}

typedef struct { int file; int parent; } AgentctlLock;

void agentctl_lock_release(void *pointer) {
  AgentctlLock *lock = pointer;
  flock(lock->file, LOCK_UN);
  close(lock->file);
  close(lock->parent);
  free(lock);
}

void *agentctl_lock_take(const char *directory, const char *name, long long *owner, int *error) {
  int parent = -1, file = -1;
  struct stat info;
  AgentctlLock *lock = NULL;
  *owner = 0;
  *error = 0;
  if (!private_name(name)) { errno = EINVAL; goto failure; }
  parent = open(directory, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  if (parent < 0 || fstat(parent, &info)) goto failure;
  if (!S_ISDIR(info.st_mode) || info.st_uid != geteuid() || (info.st_mode & 07777U) != 0700U) { errno = EACCES; goto failure; }
  file = openat(parent, name, O_RDWR | O_CREAT | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK, 0600);
  if (file < 0 || fstat(file, &info)) goto failure;
  if (!S_ISREG(info.st_mode) || info.st_uid != geteuid() || (info.st_mode & 07777U) != 0600U || info.st_nlink != 1) {
    errno = EACCES; goto failure;
  }
  if (flock(file, LOCK_EX | LOCK_NB)) {
    if (errno == EWOULDBLOCK || errno == EAGAIN) {
      char bytes[63];
      ssize_t length;
      do { length = pread(file, bytes, sizeof(bytes), 1); } while (length < 0 && errno == EINTR);
      if (length > 0) *owner = lock_owner(bytes, (size_t)length);
      *error = -1;
      goto finish;
    }
    goto failure;
  }
  char bytes[64];
  int length = snprintf(bytes, sizeof(bytes), "\n%lld\n", (long long)getpid());
  if (length <= 0 || (size_t)length >= sizeof(bytes)) { errno = EINVAL; goto failure; }
  size_t written = 0;
  while (written < (size_t)length) {
    ssize_t count = write(file, bytes + written, (size_t)length - written);
    if (count < 0 && errno == EINTR) continue;
    if (count <= 0) { if (!count) errno = EIO; goto failure; }
    written += (size_t)count;
  }
  if (ftruncate(file, length)) goto failure;
  lock = malloc(sizeof(AgentctlLock));
  if (!lock) { errno = ENOMEM; goto failure; }
  lock->file = file;
  lock->parent = parent;
  return lock;
failure:
  *error = errno;
finish:
  if (file >= 0) close(file);
  if (parent >= 0) close(parent);
  return NULL;
}

int agentctl_log_append(const char *directory, const char *name, const unsigned char *bytes, size_t length) {
  int parent = -1, file = -1, error = 0;
  struct stat info;
  if (!private_name(name)) return EINVAL;
  parent = open(directory, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  if (parent < 0 || fstat(parent, &info)) goto failure;
  if (!S_ISDIR(info.st_mode) || info.st_uid != geteuid() || (info.st_mode & 07777U) != 0700U) { errno = EACCES; goto failure; }
  file = openat(parent, name, O_WRONLY | O_APPEND | O_CREAT | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK, 0600);
  if (file < 0 || fstat(file, &info)) goto failure;
  if (!S_ISREG(info.st_mode) || info.st_uid != geteuid() || (info.st_mode & 07777U) != 0600U || info.st_nlink != 1) {
    errno = EACCES; goto failure;
  }
  size_t written = 0;
  while (written < length) {
    size_t wanted = length - written > 65536 ? 65536 : length - written;
    ssize_t count = write(file, bytes + written, wanted);
    if (count < 0 && errno == EINTR) continue;
    if (count <= 0) { if (!count) errno = EIO; goto failure; }
    written += (size_t)count;
  }
  int flushed;
  do { flushed = fsync(file); } while (flushed < 0 && errno == EINTR);
  if (flushed) goto failure;
  goto finish;
failure:
  error = errno;
finish:
  if (file >= 0 && close(file) && !error) error = errno;
  if (parent >= 0) close(parent);
  return error;
}

static unsigned char *snapshot_file(const char *directory, const char *name, unsigned int *facts, size_t *length, int *error, int shared) {
  unsigned char *bytes = NULL;
  int parent = -1, file = -1;
  struct stat info;
  *length = 0;
  *error = 0;
  parent = open(directory, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  if (parent < 0 || fstat(parent, &info)) goto failure;
  access_facts(&info, 1, facts + 3);
  file = openat(parent, name, O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK);
  if (file < 0 || fstat(file, &info)) goto failure;
  access_facts(&info, 0, facts);
  if (info.st_size < 0 || (uint64_t)info.st_size > (shared ? SIZE_MAX - 1 : AGENTCTL_SPEC_LIMIT)) { errno = EFBIG; goto failure; }
  size_t size = facts[0] ? (size_t)info.st_size : 0;
  bytes = malloc(size + 1);
  if (!bytes) { errno = ENOMEM; goto failure; }
  while (*length < size) {
    size_t wanted = size - *length > 65536 ? 65536 : size - *length;
    ssize_t count = read(file, bytes + *length, wanted);
    if (count < 0 && errno == EINTR) continue;
    if (count <= 0) { if (!count) errno = EIO; goto failure; }
    *length += (size_t)count;
  }
  if (facts[0] && !shared) {
    unsigned char extra;
    ssize_t count;
    do { count = read(file, &extra, 1); } while (count < 0 && errno == EINTR);
    if (count != 0) { errno = EIO; goto failure; }
  }
  close(file);
  close(parent);
  return bytes;
failure:
  *error = errno;
  if (file >= 0) close(file);
  if (parent >= 0) close(parent);
  free(bytes);
  return NULL;
}


#endif

unsigned char *agentctl_spec_snapshot(const char *directory, const char *name, unsigned int *facts, size_t *length, int *error) {
  return snapshot_file(directory, name, facts, length, error, 0);
}

unsigned char *agentctl_log_snapshot(const char *directory, const char *name, unsigned int *facts, size_t *length, int *error) {
  return snapshot_file(directory, name, facts, length, error, 1);
}

void agentctl_free(void *pointer) { free(pointer); }
