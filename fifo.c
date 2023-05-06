#include <stdio.h>
#include <string.h>

#include "fifo.h"

int Q_get(Q *q, int *retval)
{
    if (q->tail == q->head)
        return -1;

    *retval = q->data[q->tail];
    q->data[q->tail] = 0;
    q->tail = (q->tail + 1) % q->size;
    return 1;
}

int Q_put(Q *q, int handle)
{
    if (((q->head + 1) % q->size) == q->tail)
        return -1;

    q->data[q->head] = handle;
    q->head = (q->head + 1) % q->size;
    return 0;
}
