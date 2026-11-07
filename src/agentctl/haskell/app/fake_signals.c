/* Copyright (c) 2026 agentctl contributors. */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif
#include <errno.h>
#include <stddef.h>
#include <signal.h>

#ifdef _WIN32
#include <windows.h>
#include <limits.h>

int agentctl_fake_console_write(const char *bytes, size_t length) {
  HANDLE output = GetStdHandle(STD_OUTPUT_HANDLE);
  DWORD mode;
  if (!GetConsoleMode(output, &mode)) return -1;
  if (length == 0) return 0;
  if (length > INT_MAX) return ERROR_INVALID_PARAMETER;
  int count = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, bytes, (int)length, NULL, 0);
  if (count == 0) return (int)GetLastError();
  WCHAR *wide = HeapAlloc(GetProcessHeap(), 0, (size_t)count * sizeof(WCHAR));
  if (wide == NULL) return ERROR_NOT_ENOUGH_MEMORY;
  int error = 0;
  if (!MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, bytes, (int)length, wide, count)) {
    error = (int)GetLastError();
  } else {
    DWORD offset = 0;
    while (offset < (DWORD)count) {
      DWORD written = 0;
      if (!WriteConsoleW(output, wide + offset, (DWORD)count - offset, &written, NULL)) {
        error = (int)GetLastError();
        break;
      }
      if (written == 0) { error = ERROR_WRITE_FAULT; break; }
      offset += written;
    }
  }
  HeapFree(GetProcessHeap(), 0, wide);
  return error;
}
static HANDLE input_handle = INVALID_HANDLE_VALUE;
static DWORD input_mode;
static UINT input_page;
static int input_changed = 0;

int agentctl_fake_raw_begin(void) {
  input_changed = 0;
  input_handle = GetStdHandle(STD_INPUT_HANDLE);
  if (!GetConsoleMode(input_handle, &input_mode)) {
    int error = (int)GetLastError();
    return GetFileType(input_handle) == FILE_TYPE_PIPE ? 0 : error;
  }
  DWORD mode = input_mode & ~(ENABLE_LINE_INPUT | ENABLE_ECHO_INPUT | ENABLE_PROCESSED_INPUT);
  input_page = GetConsoleCP();
  if (!SetConsoleCP(CP_UTF8)) return (int)GetLastError();
  if (!SetConsoleMode(input_handle, mode)) {
    int error = (int)GetLastError();
    SetConsoleCP(input_page);
    return error;
  }
  input_changed = 1;
  return 0;
}

int agentctl_fake_raw_end(void) {
  int error = 0;
  if (input_changed) {
    if (!SetConsoleMode(input_handle, input_mode)) error = (int)GetLastError();
    if (!SetConsoleCP(input_page) && error == 0) error = (int)GetLastError();
  }
  input_changed = 0;
  return error;
}

int agentctl_fake_input_ready(void) {
  HANDLE handle = GetStdHandle(STD_INPUT_HANDLE);
  if (GetFileType(handle) == FILE_TYPE_PIPE) {
    DWORD available = 0;
    if (!PeekNamedPipe(handle, NULL, 0, NULL, &available, NULL))
      return GetLastError() == ERROR_BROKEN_PIPE ? 1 : -1;
    return available > 0;
  }
  for (;;) {
    INPUT_RECORD record;
    DWORD count = 0;
    if (!PeekConsoleInputW(handle, &record, 1, &count)) return -1;
    if (count == 0) return 0;
    if (record.EventType == KEY_EVENT && record.Event.KeyEvent.bKeyDown &&
        record.Event.KeyEvent.uChar.UnicodeChar != 0) return 1;
    if (!ReadConsoleInputW(handle, &record, 1, &count)) return -1;
  }
}
#else
#include <termios.h>
#include <unistd.h>
int agentctl_fake_console_write(const char *bytes, size_t length) {
  (void)bytes;
  (void)length;
  return -1;
}
static struct termios input_mode;
static int input_changed = 0;

int agentctl_fake_raw_begin(void) {
  input_changed = 0;
  if (tcgetattr(STDIN_FILENO, &input_mode)) return errno == ENOTTY ? 0 : errno;
  struct termios mode = input_mode;
  mode.c_iflag &= ~(IGNBRK | BRKINT | PARMRK | ISTRIP | INLCR | IGNCR | ICRNL | IXON);
  mode.c_lflag &= ~(ECHO | ECHONL | ICANON | ISIG | IEXTEN);
  mode.c_cflag = (mode.c_cflag & ~(CSIZE | PARENB)) | CS8;
  mode.c_cc[VMIN] = 1;
  mode.c_cc[VTIME] = 0;
  if (tcsetattr(STDIN_FILENO, TCSANOW, &mode)) return errno;
  input_changed = 1;
  return 0;
}

int agentctl_fake_raw_end(void) {
  int error = input_changed && tcsetattr(STDIN_FILENO, TCSANOW, &input_mode) ? errno : 0;
  input_changed = 0;
  return error;
}

int agentctl_fake_input_ready(void) { return 1; }
#endif

static volatile sig_atomic_t reap_received = 0;

#ifndef _WIN32
static void observe_reap(int number) {
  if (number == SIGCHLD) reap_received = 1;
}
#endif

int agentctl_fake_watch_reap(void) {
  reap_received = 0;
#ifdef _WIN32
  return 0;
#else
  return signal(SIGCHLD, observe_reap) == SIG_ERR ? errno : 0;
#endif
}

int agentctl_fake_reap_received(void) { return reap_received; }

int agentctl_fake_ignore_hangup(void) {
#ifdef _WIN32
  return 0;
#else
  return signal(SIGHUP, SIG_IGN) == SIG_ERR ? errno : 0;
#endif
}
