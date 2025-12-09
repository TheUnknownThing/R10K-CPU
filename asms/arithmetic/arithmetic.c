int main() {
    int a = 10;
    int b = 20;
    int c = a + b; // 30
    int d = b - a; // 10
    int e = 0;
    
    // Test conditional branch
    if (c > d) {
        e = c;
    } else {
        e = d;
    }
    
    // Test loop
    int sum = 0;
    for (int i = 0; i < 5; i++) {
        sum += i;
    }
    
    return e + sum; // 30 + 10 = 40
}
