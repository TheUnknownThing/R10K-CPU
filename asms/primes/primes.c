#define LIMIT 1000
int is_prime[LIMIT]; // 0 for prime (default), 1 for not prime

int main() {
    int i, j;
    
    // 0 and 1 are not prime
    is_prime[0] = 1;
    is_prime[1] = 1;
    
    // Sieve of Eratosthenes
    // We use i < 32 because 32*32 = 1024 > 1000
    for (i = 2; i < 32; i++) {
        if (is_prime[i] == 0) {
            // Start from 2*i to avoid multiplication if possible, 
            // but i*i is better optimization. 
            // Since we don't have hardware mul, let's just use repeated addition 
            // or start from i+i.
            for (j = i + i; j < LIMIT; j += i) {
                is_prime[j] = 1;
            }
        }
    }
    
    int count = 0;
    for (i = 0; i < LIMIT; i++) {
        if (is_prime[i] == 0) {
            count++;
        }
    }
    return count; // 168
}
