#include <stdbool.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/signal.h>
#include <sys/ioctl.h>
#include <pthread.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>
#include <sys/select.h>
#include <fcntl.h>

#include "fifo.h"

#define QUEUE_SIZE 10
// #define DEBUG


int running = 1;


void sig_handler(int signum)
{
    running = 0;
}

void *kb_event(void *arg)
{
    Q *q = (Q *) arg;
    struct timeval tv;
    fd_set fds;

    tv.tv_sec = 0;
    tv.tv_usec = 10000;

    while (running) {
        FD_ZERO(&fds);
        FD_SET(STDIN_FILENO, &fds);
        select(STDIN_FILENO+1, &fds, NULL, NULL, &tv);
        int ret = FD_ISSET(STDIN_FILENO, &fds);
#ifdef DEBUG
        fprintf(stdout, "kb_event | ret=%d\n", ret);
#endif
        if (ret < 0) {
            return NULL;
        } else if (ret == 0) {
            continue;
        }

        int c = getchar();
#ifdef DEBUG
        fprintf(stdout, "kb_event | getchar()=%d\n", ret);
#endif
        if (c == EOF) {
            return NULL;
        }
        Q_put(q, c);
    }
    return NULL;
}


int main(int argc, const char **argv)
{
    signal(SIGINT, sig_handler);

    // clear screen
    fprintf(stdout, "\033[2J");
    // hide cursor
    fprintf(stdout, "\033[?25l");

    // tty raw mode, non buffered io
    struct termios oldt, newt;
    tcgetattr(STDIN_FILENO, &oldt);
    memcpy(&newt, &oldt, sizeof(struct termios));
    newt.c_lflag &= ~(ICANON | ECHO);
    newt.c_cc[VMIN] = 1;
    tcsetattr(STDIN_FILENO, TCSANOW, &newt);

    int data[QUEUE_SIZE] = {0};
    Q q = { .head = 0, .tail = 0, .size = QUEUE_SIZE, .data = data};

    // io thread init
    pthread_t io_thread;
    pthread_create(&io_thread, NULL, kb_event, &q);

    while (running) {
        int c = 0;
        int rc = Q_get(&q, &c);
#ifdef DEBUG
        fprintf(stdout, "main | Q_get()=%d\n", rc);
#endif
        if (rc < 0) {
            continue;
        }

        if (c == EOF) {
            running = 0;
        } else if (c == 0) {
            ;
        } else if (c >= 32 && c <= 126) {
            fprintf(stdout, "\e[0;32m%d\n", c);
        } else {
            fprintf(stdout, "\e[0;31m%d\n", c);
        }
        fprintf(stdout, "\e[0m");
    }

    // main processing loop
    fprintf(stdout, "end io_thread\n");

    // terminal cleanup
    // restore terminal settings
    tcsetattr(STDIN_FILENO, TCSANOW, &oldt);
    // end color
    fprintf(stdout, "\033[0m");
    // show cursor
    fprintf(stdout, "\033[?25h");
    // restore screen
    fprintf(stdout, "\033[?47l");

    return 0;
}
