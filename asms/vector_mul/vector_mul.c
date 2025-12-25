#define DATA_SIZE 100

int input_data1[DATA_SIZE];
int input_data2[DATA_SIZE];
int results_data[DATA_SIZE];

int main() {
    int i;
    // Initialize data
    for (i = 0; i < DATA_SIZE; i++) {
        input_data1[i] = i;
        input_data2[i] = 2;
    }

    // Perform multiplication
    for (i = 0; i < DATA_SIZE; i++) {
        results_data[i] = input_data1[i] * input_data2[i];
    }

    // Verify
    int sum = 0;
    for (i = 0; i < DATA_SIZE; i++) {
        sum += results_data[i];
    }
    // sum = sum(i * 2) for i in 0..99
    // sum = 2 * sum(0..99) = 2 * (99 * 100 / 2) = 9900
    return sum;
}
