int arr[10] = {5, 2, 9, 1, 5, 6, 10, 3, 8, 4};

int main() {
    int n = 10;
    int i, j, temp;
    for (i = 0; i < n - 1; i++) {
        for (j = 0; j < n - i - 1; j++) {
            if (arr[j] > arr[j + 1]) {
                temp = arr[j];
                arr[j] = arr[j + 1];
                arr[j + 1] = temp;
            }
        }
    }
    // Sorted: 1, 2, 3, 4, 5, 5, 6, 8, 9, 10
    return arr[0] + arr[9]; // 1 + 10 = 11
}
