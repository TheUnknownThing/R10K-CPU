typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;

volatile u8 byte_buf[8];
volatile u16 half_buf[4];

int main(void) {
    byte_buf[0] = 0x11;
    byte_buf[1] = 0x22;
    byte_buf[2] = 0x33;
    byte_buf[3] = 0x44;
    byte_buf[4] = 0x80;
    byte_buf[5] = 0x7F;

    u32 byte_acc = 0;
    byte_acc += byte_buf[0];
    byte_acc += ((u32)byte_buf[1]) << 1;
    byte_acc += ((u32)byte_buf[2]) << 2;
    byte_acc += ((u32)byte_buf[3]) << 3;
    byte_acc += byte_buf[4];
    byte_acc += byte_buf[5];

    half_buf[0] = 0x0123;
    half_buf[1] = 0x4567;
    half_buf[2] = 0x89AB;

    u32 half_acc = 0;
    half_acc += half_buf[0];
    half_acc += half_buf[1];
    half_acc += half_buf[2];

    return (int)(byte_acc + half_acc);
}
