// https://gist.github.com/ryankurte/61f95dc71133561ed055ff62b33585f8// A simple fifo queue (or ring buffer) in c.
// This implementation \should be\ "thread safe" for single producer/consumer with atomic writes of size_t.
// This is because the head and tail "pointers" are only written by the producer and consumer respectively.
// Demonstrated with void pointers and no memory management.
// Note that empty is head==tail, thus only QUEUE_SIZE-1 entries may be used.

#ifndef FIFO_H
#define FIFO_H

#include <stdlib.h>

typedef struct {
    size_t head;
    size_t tail;
    size_t size;
    int *data;
} Q;

int Q_get(Q *, int *);
int Q_put(Q *, int);

#endif
