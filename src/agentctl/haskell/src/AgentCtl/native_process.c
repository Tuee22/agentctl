/* Copyright (c) 2026 agentctl contributors. */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif
#include <errno.h>
#include <limits.h>
#include <stdlib.h>
#include <signal.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#include <direct.h>
#include <process.h>
#include "native_utf8.h"

long long agentctl_pid(void) { return (long long)GetCurrentProcessId(); }
static void free_vector(wchar_t **values) {
  if (!values) return;
  for (size_t index = 0; values[index]; ++index) free(values[index]);
  free(values);
}

static wchar_t **wide_vector(char *const *values) {
  size_t count = 0;
  while (values[count]) ++count;
  wchar_t **result = calloc(count + 1, sizeof(wchar_t *));
  if (!result) { errno = ENOMEM; return NULL; }
  for (size_t index = 0; index < count; ++index) {
    result[index] = wide(values[index]);
    if (!result[index]) { free_vector(result); return NULL; }
  }
  return result;
}

int agentctl_exec(const char *executable, const char *directory, char *const *arguments, char *const *environment) {
  wchar_t *path = wide(executable), *cwd = wide(directory);
  wchar_t **argv = wide_vector(arguments), **env = wide_vector(environment);
  int error;
  if (path && cwd && argv && env && _wchdir(cwd) == 0) _wexecve(path, (const wchar_t *const *)argv, (const wchar_t *const *)env);
  error = errno;
  free_vector(env); free_vector(argv); free(cwd); free(path);
  return error;
}

#else
#include <unistd.h>
long long agentctl_pid(void) { return (long long)getpid(); }
int agentctl_exec(const char *executable, const char *directory, char *const *arguments, char *const *environment) {
  if (chdir(directory) == 0) execve(executable, arguments, environment);
  return errno;
}
#endif

#define AGENTCTL_SIGNAL(value) if (strcmp(name, #value) == 0) return SIG##value
int agentctl_signal_number(const char *name) {
#ifdef SIGHUP
  AGENTCTL_SIGNAL(HUP);
#endif
#ifdef SIGINT
  AGENTCTL_SIGNAL(INT);
#endif
#ifdef SIGQUIT
  AGENTCTL_SIGNAL(QUIT);
#endif
#ifdef SIGILL
  AGENTCTL_SIGNAL(ILL);
#endif
#ifdef SIGTRAP
  AGENTCTL_SIGNAL(TRAP);
#endif
#ifdef SIGABRT
  AGENTCTL_SIGNAL(ABRT);
#endif
#ifdef SIGBUS
  AGENTCTL_SIGNAL(BUS);
#endif
#ifdef SIGFPE
  AGENTCTL_SIGNAL(FPE);
#endif
#ifdef SIGKILL
  AGENTCTL_SIGNAL(KILL);
#endif
#ifdef SIGUSR1
  AGENTCTL_SIGNAL(USR1);
#endif
#ifdef SIGSEGV
  AGENTCTL_SIGNAL(SEGV);
#endif
#ifdef SIGUSR2
  AGENTCTL_SIGNAL(USR2);
#endif
#ifdef SIGPIPE
  AGENTCTL_SIGNAL(PIPE);
#endif
#ifdef SIGALRM
  AGENTCTL_SIGNAL(ALRM);
#endif
#ifdef SIGTERM
  AGENTCTL_SIGNAL(TERM);
#endif
#ifdef SIGCHLD
  AGENTCTL_SIGNAL(CHLD);
#endif
#ifdef SIGCONT
  AGENTCTL_SIGNAL(CONT);
#endif
#ifdef SIGSTOP
  AGENTCTL_SIGNAL(STOP);
#endif
#ifdef SIGTSTP
  AGENTCTL_SIGNAL(TSTP);
#endif
#ifdef SIGTTIN
  AGENTCTL_SIGNAL(TTIN);
#endif
#ifdef SIGTTOU
  AGENTCTL_SIGNAL(TTOU);
#endif
#ifdef SIGURG
  AGENTCTL_SIGNAL(URG);
#endif
#ifdef SIGXCPU
  AGENTCTL_SIGNAL(XCPU);
#endif
#ifdef SIGXFSZ
  AGENTCTL_SIGNAL(XFSZ);
#endif
#ifdef SIGVTALRM
  AGENTCTL_SIGNAL(VTALRM);
#endif
#ifdef SIGPROF
  AGENTCTL_SIGNAL(PROF);
#endif
#ifdef SIGWINCH
  AGENTCTL_SIGNAL(WINCH);
#endif
#ifdef SIGIO
  AGENTCTL_SIGNAL(IO);
#endif
#ifdef SIGPWR
  AGENTCTL_SIGNAL(PWR);
#endif
#ifdef SIGSYS
  AGENTCTL_SIGNAL(SYS);
#endif
#ifdef SIGEMT
  AGENTCTL_SIGNAL(EMT);
#endif
#ifdef SIGINFO
  AGENTCTL_SIGNAL(INFO);
#endif
#ifdef SIGTHR
  AGENTCTL_SIGNAL(THR);
#endif
#ifdef SIGLOST
  AGENTCTL_SIGNAL(LOST);
#endif
  return 0;
}
#undef AGENTCTL_SIGNAL

int agentctl_request_reap(long long server_pid) {
  if (server_pid <= 0 || server_pid > INT_MAX) return EINVAL;
#ifdef _WIN32
  return ENOSYS;
#else
  return kill((pid_t)server_pid, SIGCHLD) == 0 ? 0 : errno;
#endif
}

