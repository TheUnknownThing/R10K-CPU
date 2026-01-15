
int main() {
    volatile int result = 0;
    volatile int i;
    for (i = 0; i <= 100; i++) {
        volatile int num = i * (i + 1);
        volatile int den = (i % 5) + 1;
        volatile int div = num / den - 2;
        volatile int final = (i * div) % 4;
        volatile int shift = (i % 3) + 1;
        result += (final << shift);
    }
    return result % 127;
}
