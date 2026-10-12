#pragma once

#include <stddef.h>

#include <string>

// Copies everything the server writes to stderr into dated files (newserv-YYYY-MM-DD.log) in the given directory, in
// addition to stderr itself. This exists so that logs survive the container being recreated: stderr goes to the
// container runtime's log, which is discarded whenever the container is replaced, but the directory can be on a
// persistent volume. Files older than retention_days are deleted when a new day's file is opened (0 = keep forever).
//
// Call this once, as early as possible, before anything else is running. Does nothing on Windows.
void start_log_file(const std::string& directory, size_t retention_days);
