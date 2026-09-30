package com.example.unmapped;

import org.apache.ibatis.annotations.Mapper;
import java.util.List;

@Mapper
public interface UnmappedMapper {
    List<Object> findAll();
}
