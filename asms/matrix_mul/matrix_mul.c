#define N 8

int A[N][N];
int B[N][N];
int C[N][N];

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
                sum += A[i][k] * B[k][j];
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
