    .global _start
_start:
    li sp, 0x10000
    call main 
    sb x0, -1(x0)
1: 
    j 1b
