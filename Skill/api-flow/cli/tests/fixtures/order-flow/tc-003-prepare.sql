SET @product_id = UUID();
INSERT INTO product (id, name, stock, price) VALUES (@product_id, '限量产品', 1, 999.00);
SET @user_id = UUID();
INSERT INTO user (id, name, credit) VALUES (@user_id, '测试用户', 10000.00);
