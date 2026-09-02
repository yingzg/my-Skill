DELETE FROM orders WHERE product_id = @product_id;
DELETE FROM product WHERE id = @product_id;
DELETE FROM user WHERE id = @user_id;
