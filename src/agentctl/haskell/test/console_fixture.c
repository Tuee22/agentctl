/* Copyright (c) 2026 agentctl contributors. */
#include <errno.h>
#ifdef _WIN32
#include <windows.h>

static BOOL WINAPI ignore_control(DWORD event) {
  return event == CTRL_C_EVENT || event == CTRL_BREAK_EVENT;
}

int agentctl_fixture_console_ignore(void) {
  return SetConsoleCtrlHandler(ignore_control, TRUE) ? 0 : (int)GetLastError();
}

int agentctl_fixture_console_signal(long long pid, int interrupt) {
  if (pid <= 0 || pid > MAXDWORD || (DWORD)pid == GetCurrentProcessId()) return ERROR_INVALID_PARAMETER;
  DWORD processes[128];
  DWORD count = GetConsoleProcessList(processes, 128);
  if (!count) return (int)GetLastError();
  if (count > 128) return ERROR_INSUFFICIENT_BUFFER;
  int member = 0;
  for (DWORD index = 0; index < count; ++index) if (processes[index] == (DWORD)pid) member = 1;
  if (!member) return ERROR_ACCESS_DENIED;
  return GenerateConsoleCtrlEvent(interrupt ? CTRL_C_EVENT : CTRL_BREAK_EVENT, interrupt ? 0 : (DWORD)pid) ? 0 : (int)GetLastError();
}
#else
int agentctl_fixture_console_ignore(void) { return ENOSYS; }
int agentctl_fixture_console_signal(long long pid, int interrupt) {
  (void)pid;
  (void)interrupt;
  return ENOSYS;
}
#endif
