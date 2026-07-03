# thread_block_tile简介

`thread_block_tile`是一个模板类，用于管理指定大小的线程子组。

> [!CAUTION]注意 
> SIMT架构不支持独立线程调度，一个Warp内的各协作组间应避免存在数据依赖，否则可能出现卡死的情况。

## Public成员函数

```c++
void sync() const;
unsigned long long num_threads() const;
unsigned long long thread_rank() const;
unsigned long long meta_group_size() const;
unsigned long long meta_group_rank() const;
template <typename T>
T shfl(T var, int src_rank) const;
template <typename T>
T shfl_up(T var, unsigned int delta) const;
template <typename T>
T shfl_down(T var, unsigned int delta) const;
template <typename T>
T shfl_xor(T var, unsigned int lane_mask) const;
int any(int predicate) const;
int all(int predicate) const;
unsigned int ballot(int predicate) const;
unsigned long long size() const;
```
