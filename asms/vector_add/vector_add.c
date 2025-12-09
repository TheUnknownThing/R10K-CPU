#define DATA_SIZE 100

int a[DATA_SIZE];
int b[DATA_SIZE];
int c[DATA_SIZE];

void vvadd(int n, int a[], int b[], int c[]) {
    int i;
    for (i = 0; i < n; i++)
        c[i] = a[i] + b[i];
}

int main() {
    int i;
    // Initialize data
    for (i = 0; i < DATA_SIZE; i++) {
        a[i] = i;
        b[i] = 100 - i;
    }

    vvadd(DATA_SIZE, a, b, c);

    // Verify
    int sum = 0;
    for (i = 0; i < DATA_SIZE; i++) {
        sum += c[i];
    }
    // c[i] = i + (100 - i) = 100
    // sum = 100 * 100 = 10000
    return sum;
}
