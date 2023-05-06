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


int TERMX;
int TERMY;
int running;

typedef struct {
    float x, y;
} Vec2;

void get_term_size(Vec2 *v)
{
    // runtime terminal size
    struct winsize w;
    ioctl(STDOUT_FILENO, TIOCGWINSZ, &w);
    v->x = (float)w.ws_col * 0.5f;
    v->y = (float)w.ws_row;
    TERMX = (int) v->x;
    TERMY = (int) v->y;
}

void sig_handler(int signum)
{
    running = 0;
}

int main()
{
    running = 1;
    signal(SIGINT, sig_handler);
    Vec2 term;
    get_term_size(&term);
    int termx = TERMX;
    int termy = TERMY;

    if (termx <= 0 || termy <= 0)
        return -1;

    // clear screen
    printf("\033[2J");
    // hide cursor
    printf("\e[?25l");
    // tty raw mode, non buffered io
    struct termios mode;
    tcgetattr(0, &mode);
    mode.c_lflag &= ~(ECHO | ICANON);
    tcsetattr(0, TCSANOW, &mode);

    // io thread init
    /* pthread_t _kb_input; */
    /* Q q = { .head = 0, .tail = 0, .size = QUEUE_SIZE, .data = qp}; */
    /* pthread_create(&_kb_input, NULL, kb_input, &q); */

    while (1) {
        int c = getchar();
        printf("%d\n", c);
    }

    // show cursor
    printf("\e[?25h");
    return 0;
}
