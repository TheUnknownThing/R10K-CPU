int nums[10] = {1,2,3,4,5,6,7,8,9,10};

int main(){
    int ans = 0;
    for (int i = 0;i < 10;i++) {
        ans += nums[i];
    }
    return ans;
}