package com.example.config;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@MapperScan(basePackages = {"com.example.user.mapper", "com.example.product.mapper"})
@ConfigurationProperties(prefix = "spring.datasource.secondary")
public class DataSourceConfig {
}
