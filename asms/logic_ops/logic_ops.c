int main() {
    int a = 0x0F0F0F0F;
    int b = 0xF0F0F0F0;
    
    int and_res = a & b; // 0
    int or_res = a | b;  // 0xFFFFFFFF (-1)
    int xor_res = a ^ b; // 0xFFFFFFFF (-1)
    
    int c = 1;
    int shl_res = c << 4; // 16
    int shr_res = shl_res >> 2; // 4
    
    int res = 0;
    if (and_res == 0) res += 1;
    if (or_res == -1) res += 2;
    if (xor_res == -1) res += 4;
    if (shl_res == 16) res += 8;
    if (shr_res == 4) res += 16;
    
    return res; // 1+2+4+8+16 = 31
}
