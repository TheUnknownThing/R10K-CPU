
int main() {
    volatile int result = 0;
    volatile int a, b;
    a = 100; b = 10; result += a % b;
    a = 100; b = 3; result += a % b;
    a = -100; b = 3; result += a % b;
    a = 100; b = -3; result += a % b;
    a = -100; b = -3; result += a % b;
    a = 1; b = 0; result += a % b;
    a = -2147483648; b = -1; result += a % b;
    return result;
}
