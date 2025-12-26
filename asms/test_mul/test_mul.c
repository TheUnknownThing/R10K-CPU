
int main() {
    volatile int result = 0;
    volatile int a, b;
    a = 123; b = 456; result += a * b;
    a = 0; b = 999; result += a * b;
    a = 999; b = 0; result += a * b;
    a = 1; b = 777; result += a * b;
    a = -1; b = 777; result += a * b;
    a = 2147483647; b = 2; result += a * b;
    a = -2147483648; b = 1; result += a * b;
    a = 100; b = -5; result += a * b;
    a = -100; b = -5; result += a * b;
    return result;
}
