/* Copyright (c) 2026 agentctl contributors. */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif
#include <errno.h>
#include <signal.h>

#ifdef _WIN32
#include <windows.h>
static HANDLE input_handle = INVALID_HANDLE_VALUE;
static DWORD input_mode;
static int input_changed = 0;

int agentctl_fake_raw_begin(void) {
  input_changed = 0;
  input_handle = GetStdHandle(STD_INPUT_HANDLE);
  if (!GetConsoleMode(input_handle, &input_mode)) {
    int error = (int)GetLastError();
    return GetFileType(input_handle) == FILE_TYPE_PIPE ? 0 : error;
  }
  DWORD mode = input_mode & ~(ENABLE_LINE_INPUT | ENABLE_ECHO_INPUT | ENABLE_PROCESSED_INPUT);
  if (!SetConsoleMode(input_handle, mode)) return (int)GetLastError();
  input_changed = 1;
  return 0;
}

int agentctl_fake_raw_end(void) {
  int error = input_changed && !SetConsoleMode(input_handle, input_mode) ? (int)GetLastError() : 0;
  input_changed = 0;
  return error;
}
#else
#include <termios.h>
#include <unistd.h>
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
