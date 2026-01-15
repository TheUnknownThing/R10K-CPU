
int main() {
    volatile int result = 0;
    volatile int a, b;
    long long res_long;
    a = 10; b = 10;
    res_long = (long long)a * (long long)b;
    result += (int)(res_long >> 32); // 0
    a = 2147483647; b = 100;
    res_long = (long long)a * (long long)b;
    result += (int)(res_long >> 32); // 49
    a = 2147483647; b = 2147483647;
    res_long = (long long)a * (long long)b;
    result += (int)(res_long >> 32); // 49 + 1073741823 = 1073741872
    a = -1; b = -1;
    res_long = (long long)a * (long long)b;
    result += (int)(res_long >> 32); // 1073741872
    a = -2147483648; b = -2147483648;
    res_long = (long long)a * (long long)b;
    result += (int)(res_long >> 32); // 
    a = -2147483648; b = 1;
    res_long = (long long)a * (long long)b;
    result += (int)(res_long >> 32);
    a = -2147483648; b = -1;
    res_long = (long long)a * (long long)b;
    result += (int)(res_long >> 32);
    a = -2147483648; b = 0;
    res_long = (long long)a * (long long)b;
    result += (int)(res_long >> 32);
    a = 12345678; b = -87654321;
    res_long = (long long)a * (long long)b;
    result += (int)(res_long >> 32);
    return result;
}
