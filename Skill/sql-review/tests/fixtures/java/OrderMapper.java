package com.example.mapper;

import com.example.entity.Order;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

@Mapper
public interface OrderMapper {

    Order findById(@Param("id") Long id);

    Order findByOrderNo(@Param("orderNo") String orderNo);

    List<Order> findAll();

    int countByStatus(@Param("status") String status);

    int updateStatus(@Param("id") Long id, @Param("status") String status);

    int updateStatusNoWhere(@Param("status") String status);

    int deleteById(@Param("id") Long id);

    int deleteAll();

    int insertOrder(Order order);

    List<Order> findWithDetail(@Param("id") Long id);

    List<Order> findWithMultipleJoins(@Param("status") String status);

    List<Order> findBySubQuery();

    List<Order> findByCondition(@Param("status") String status, @Param("orderNo") String orderNo);

    List<Order> findBySingleIf(@Param("amount") Double amount);

    int updateByIf(@Param("id") Long id, @Param("status") String status, @Param("amount") Double amount);

    List<Order> findByChoose(@Param("status") String status, @Param("orderNo") String orderNo);

    List<Order> findByIds(@Param("ids") List<Long> ids);

    int batchInsert(@Param("list") List<Order> orders);

    int deleteByIds(@Param("ids") List<Long> ids);

    List<Order> findByWhere(@Param("status") String status, @Param("orderNo") String orderNo,
                            @Param("amount") Double amount);

    int updateBySet(@Param("id") Long id, @Param("status") String status, @Param("amount") Double amount);

    List<Order> findByTrim(@Param("status") String status, @Param("orderNo") String orderNo);

    int updateByTrimSet(@Param("id") Long id, @Param("status") String status, @Param("amount") Double amount);

    List<Order> findByBind(@Param("keyword") String keyword);

    List<Order> findByBindWithIf(@Param("keyword") String keyword);

    List<Order> findWithInclude(@Param("status") String status, @Param("user_id") Long userId);

    List<Order> findByMixed(@Param("statusList") List<String> statusList,
                            @Param("minAmount") Double minAmount,
                            @Param("maxAmount") Double maxAmount);
}
