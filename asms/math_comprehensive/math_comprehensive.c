
int main() {
    volatile int result = 0;
    volatile int i;
    for (i = 0; i <= 100; i++) {
        volatile int num = i * (i + 1);
        volatile int den = (i % 5) + 1;
        result += num / den;
    }
    return result;
}
