/* Copyright (c) 2026 agentctl contributors. */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif
#include <errno.h>
#include <signal.h>
#include <stdatomic.h>
#include <string.h>

static atomic_flag active = ATOMIC_FLAG_INIT;

#ifdef _WIN32
#include <windows.h>

static volatile LONG requested = 0;
static void (*old_interrupt)(int);
static void (*old_terminate)(int);

static void stop_signal(int number) {
  (void)number;
  InterlockedExchange(&requested, 1);
}

static BOOL WINAPI stop_console(DWORD event) {
  if (event != CTRL_C_EVENT && event != CTRL_BREAK_EVENT) return FALSE;
  InterlockedExchange(&requested, 1);
  return TRUE;
}

int agentctl_stop_begin(void) {
  if (atomic_flag_test_and_set(&active)) return EBUSY;
  InterlockedExchange(&requested, 0);
  old_interrupt = signal(SIGINT, stop_signal);
  if (old_interrupt == SIG_ERR) goto failure;
  old_terminate = signal(SIGTERM, stop_signal);
  if (old_terminate == SIG_ERR) { signal(SIGINT, old_interrupt); goto failure; }
  if (!SetConsoleCtrlHandler(stop_console, TRUE)) {
    int error = (int)GetLastError();
    signal(SIGTERM, old_terminate);
    signal(SIGINT, old_interrupt);
    atomic_flag_clear(&active);
    return error;
  }
  return 0;
failure:
  atomic_flag_clear(&active);
  return errno;
}

int agentctl_stop_requested(void) { return InterlockedCompareExchange(&requested, 0, 0) != 0; }

int agentctl_stop_end(void) {
  int error = SetConsoleCtrlHandler(stop_console, FALSE) ? 0 : (int)GetLastError();
  if (signal(SIGTERM, old_terminate) == SIG_ERR && !error) error = errno;
  if (signal(SIGINT, old_interrupt) == SIG_ERR && !error) error = errno;
  atomic_flag_clear(&active);
  return error;
}

#else

static volatile sig_atomic_t requested = 0;
static struct sigaction old_interrupt, old_terminate;

static void stop_signal(int number) {
  (void)number;
  requested = 1;
}

int agentctl_stop_begin(void) {
  if (atomic_flag_test_and_set(&active)) return EBUSY;
  requested = 0;
  struct sigaction action;
  memset(&action, 0, sizeof(action));
  action.sa_handler = stop_signal;
  sigemptyset(&action.sa_mask);
  action.sa_flags = SA_RESTART;
  if (sigaction(SIGINT, &action, &old_interrupt)) goto failure;
  if (sigaction(SIGTERM, &action, &old_terminate)) {
    int error = errno;
    sigaction(SIGINT, &old_interrupt, NULL);
    errno = error;
    goto failure;
  }
  return 0;
failure:
  atomic_flag_clear(&active);
  return errno;
}

int agentctl_stop_requested(void) { return requested != 0; }

int agentctl_stop_end(void) {
  int error = sigaction(SIGTERM, &old_terminate, NULL) ? errno : 0;
  if (sigaction(SIGINT, &old_interrupt, NULL) && !error) error = errno;
  atomic_flag_clear(&active);
  return error;
}

#endif
