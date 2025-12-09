#define SIZE 100
int arr[SIZE];

void swap(int* a, int* b) {
    int t = *a;
    *a = *b;
    *b = t;
}

int partition(int arr[], int low, int high) {
    int pivot = arr[high];
    int i = (low - 1);
    for (int j = low; j <= high - 1; j++) {
        if (arr[j] < pivot) {
            i++;
            swap(&arr[i], &arr[j]);
        }
    }
    swap(&arr[i + 1], &arr[high]);
    return (i + 1);
}

void quickSort(int arr[], int low, int high) {
    if (low < high) {
        int pi = partition(arr, low, high);
        quickSort(arr, low, pi - 1);
        quickSort(arr, pi + 1, high);
    }
}

int main() {
    int i;
    // Initialize with reverse sorted data
    for(i=0; i<SIZE; i++) {
        arr[i] = SIZE - i; // 100, 99, ..., 1
    }
    
    quickSort(arr, 0, SIZE-1);
    
    // Verify
    int sum = 0;
    for(i=0; i<SIZE; i++) {
        // Check if sorted
        if (i > 0 && arr[i] < arr[i-1]) return -1;
        sum += arr[i];
    }
    return sum; // 5050
}
