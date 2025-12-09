#define N 8

int A[N][N];
int B[N][N];
int C[N][N];

int multiply(int a, int b) {
    int result = 0;
    int neg = 0;
    if (a < 0) { a = -a; neg = !neg; }
    if (b < 0) { b = -b; neg = !neg; }
    
    while (b > 0) {
        if (b & 1) result += a;
        a <<= 1;
        b >>= 1;
    }
    
    return neg ? -result : result;
}

int main() {
    int i, j, k;
    // Init
    for(i=0; i<N; i++) {
        for(j=0; j<N; j++) {
            A[i][j] = i + j;
            B[i][j] = i + 1;
        }
    }

    // Mul
    for(i=0; i<N; i++) {
        for(j=0; j<N; j++) {
            int sum = 0;
            for(k=0; k<N; k++) {
                sum += multiply(A[i][k], B[k][j]);
            }
            C[i][j] = sum;
        }
    }

    // Checksum
    int total = 0;
    for(i=0; i<N; i++) {
        for(j=0; j<N; j++) {
            total += C[i][j];
        }
    }
    return total; // 18816
}
