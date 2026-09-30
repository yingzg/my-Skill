package com.example.mapper;

import com.baomidou.dynamic.datasource.annotation.DS;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import java.util.List;

@DS("primary")
@Mapper
public interface OrderMapper {
    List<Object> findById(@Param("id") Long id);
    int updateStatus(@Param("id") Long id, @Param("status") String status);
}
