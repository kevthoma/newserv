#include "LogFile.hh"

#include <phosg/Platform.hh>

#include <stdio.h>
#include <string.h>
#include <time.h>

#include <filesystem>
#include <thread>

#include "Loggers.hh"

#ifndef PHOSG_WINDOWS
#include <errno.h>
#include <unistd.h>

static std::string local_date_str(time_t t) {
  struct tm tm;
  localtime_r(&t, &tm);
  char buf[16];
  strftime(buf, sizeof(buf), "%Y-%m-%d", &tm);
  return buf;
}

static void prune_old_log_files(const std::filesystem::path& directory, size_t retention_days) {
  if (retention_days == 0) {
    return;
  }
  // File names embed the date as YYYY-MM-DD, so string comparison orders them correctly
  std::string cutoff_name = "newserv-" + local_date_str(time(nullptr) - retention_days * 86400) + ".log";
  std::error_code ec;
  for (const auto& entry : std::filesystem::directory_iterator(directory, ec)) {
    std::string name = entry.path().filename().string();
    if ((name.size() == cutoff_name.size()) && name.starts_with("newserv-") && name.ends_with(".log") &&
        (name < cutoff_name)) {
      std::filesystem::remove(entry.path(), ec);
    }
  }
}

static void write_all(int fd, const char* data, size_t size) {
  while (size > 0) {
    ssize_t written = write(fd, data, size);
    if (written < 0) {
      if (errno == EINTR) {
        continue;
      }
      return; // Nowhere left to report this; drop the data rather than block the server
    }
    data += written;
    size -= written;
  }
}

static int original_stderr_fd = -1;
static std::thread copy_thread;

static void copy_stderr(int read_fd, std::filesystem::path directory, size_t retention_days) {
  std::string current_date;
  FILE* f = nullptr;
  char buf[0x10000];
  for (;;) {
    ssize_t bytes_read = read(read_fd, buf, sizeof(buf));
    if (bytes_read < 0) {
      if (errno == EINTR) {
        continue;
      }
      break;
    }
    if (bytes_read == 0) {
      break; // stderr was restored at exit and everything written before that has been copied
    }

    write_all(original_stderr_fd, buf, bytes_read);

    std::string date = local_date_str(time(nullptr));
    if (date != current_date) {
      if (f) {
        fclose(f);
      }
      f = fopen((directory / ("newserv-" + date + ".log")).string().c_str(), "ab");
      current_date = date;
      prune_old_log_files(directory, retention_days);
    }
    if (f) {
      fwrite(buf, 1, bytes_read, f);
      fflush(f);
    }
  }
  if (f) {
    fclose(f);
  }
  close(read_fd);
}

static void stop_log_file() {
  // Point stderr back at the original destination. That closes the pipe's only write end, so the copy thread drains
  // whatever is still buffered, sees EOF, and exits - so the last lines before a normal exit reach the file too.
  fflush(stderr);
  dup2(original_stderr_fd, STDERR_FILENO);
  if (copy_thread.joinable()) {
    copy_thread.join();
  }
}

void start_log_file(const std::string& directory, size_t retention_days) {
  if (original_stderr_fd >= 0) {
    return;
  }

  std::error_code ec;
  std::filesystem::create_directories(directory, ec);
  if (ec) {
    config_log.error_f("Cannot create log file directory {}: {}; logging to stderr only", directory, ec.message());
    return;
  }

  int pipe_fds[2];
  if (pipe(pipe_fds) != 0) {
    config_log.error_f("Cannot create log file pipe: {}; logging to stderr only", strerror(errno));
    return;
  }
  original_stderr_fd = dup(STDERR_FILENO);
  if (original_stderr_fd < 0) {
    config_log.error_f("Cannot duplicate stderr: {}; logging to stderr only", strerror(errno));
    close(pipe_fds[0]);
    close(pipe_fds[1]);
    return;
  }

  fflush(stderr);
  dup2(pipe_fds[1], STDERR_FILENO);
  close(pipe_fds[1]);
  copy_thread = std::thread(copy_stderr, pipe_fds[0], std::filesystem::path(directory), retention_days);
  atexit(stop_log_file);

  if (retention_days) {
    config_log.info_f("Writing a copy of this log to {}/newserv-YYYY-MM-DD.log (kept for {} days)",
        directory, retention_days);
  } else {
    config_log.info_f("Writing a copy of this log to {}/newserv-YYYY-MM-DD.log (kept forever)", directory);
  }
}

#else

void start_log_file(const std::string& directory, size_t) {
  config_log.warning_f("LogFileDirectory ({}) is not supported on Windows; logging to stderr only", directory);
}

#endif
