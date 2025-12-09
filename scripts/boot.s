    .global _start
_start:
    li sp, 0x10000
    call main 
    ebreak
1: 
    j 1b
