# Commerce System Demo

## 1. Task description
Create a service which handles operations on products in an E-commerce system.

## 2. Functional requirements

### 2.1. Models
* There should be two models - Product and Category.
* Text fields should be able to support short text input, which may not be in English/Bulgarian only.
* Text fields the established practices in existing systems.
* Additional fields may be added to models in the future.

#### 2.1.1 Product model
* title - text field
* description - text field
* image
* unique product identifier (SKU)
* price. Should not lose precision when rounded.
* category - link to a category model. Can be empty.

#### 2.1.2 Category model
* name - text field
* parent - link to category model. Maximum depth of nesting of children under parent is 100.

### 2.2. Operations
* CRUD operations for both models.
* API endpoint to search and filter all products matching:
    * certain name/SKU
    * within a price range
    * under a certain category.
    * additional filters may be added
* Range borders are inclusive.
* Returned results do not need to be sorted.
* Search for a certain category should return child categories results too.
* On deletion of the category all linked to it products are to be unlinked. 
* On deletion of the parent category the children categories are to be deleted and all linked products are to be unlinked.

## 3. Non-Functional Requirements
* Use FastAPI or Django frameworks
* Unit tests for the search functionality
* The expectation is that endpoints return results within 200ms. If there are technical difficulties in achieving such latency, the reasons should be justified.
* Expected number of products: tens of thousands
* Expected number of categories: thousands
* Users per day: thousands
* No need for user authorization
* Multiple parallel connections to service

## 4. Requirements Refinement Decisions

### 4.1. FastAPI or Django framework
The **FastAPI** was chosen:
* Supports `async/await` throughout, enabling parallel DB queries and concurrent connections without threading overhead - according to the requirements for `low latency` and `multiple parallel connections`
* Built-in validation via [Pydantic](https://docs.pydantic.dev/latest/) to be used for input data contraints
* Auto-generated docs via OpenAPI/Swagger UI out of the box ([FastAPI docs](https://fastapi.tiangolo.com/features/))
* Easier to pick up compared to Django with great example-driven documentation.
* Django would be preferable if ORM ecosystem, admin panel, or auth are required.
* References:
   * [Django vs. FastAPI: A Comparison](https://blog.jetbrains.com/pycharm/2023/12/django-vs-fastapi-which-is-the-best-python-web-framework/#django-vs.-fastapi-a-comparison)
   * [A Close Look at a FastAPI Example Application](https://realpython.com/fastapi-python-web-apis/)
   * [Get Started With Django: Build a Portfolio App](https://realpython.com/get-started-with-django-1/)

### 4.2. Constraints to text fields according to the established practices in existing systems
* Use [UTF-8 encoding](https://en.wikipedia.org/wiki/UTF-8) capable of representing all Unicode characters
* `Product.title` : 255 chars (`VARCHAR(255)`)
* `Product.description` : 10000 chars (`TEXT`)
* `Category.name`: 255 chars (`VARCHAR(255)`)
* References:
   * [Shopify Product description](https://shopify.dev/docs/api/admin-graphql/latest/objects/Product#field-Product.fields.description)
   * [Shopify Product Description Length: Best Practices for SEO and Conversions](https://lettercounter.org/blog/shopify-product-description-length/)

### 4.3. The format and the storage of the image is to be chosen following the established practices in existing systems
* Store a URL string (`VARCHAR(2083)`)
* Storing binary image data in the database worsens query performance, increases backup sizes and traffic.
* Accepted formats: JPEG (universal), PNG (universal), WebP (modern optimized delivery).
* References:
   * [Shopify Product Image resource](https://shopify.dev/docs/api/admin-rest/2024-01/resources/product-image)
   * [What is the Best URL Length Limit for SEO: Maximum URL Length Characters](https://serpstat.com/blog/how-long-should-be-the-page-url-length-for-seo/)

### 4.4. The format for the unique product identifier (SKU) is to be chosen following the established practices in existing systems
* Alphanumeric string (`VARCHAR(100)`)
* Must be unique per system (`UNIQUE` constraint in DB)
* Must be present (`NOT NULL` constraint in DB)
* Normalized to upper-case on write to prevent duplicates
* Validation regex: `^[A-Z0-9_-]{1,100}$` (enforce at the API layer via Pydantic)
* References:
   * [Understanding SKU formats](https://support.ecwid.com/hc/en-us/articles/360011125640-Understanding-SKU-formats)
   * [Shopify SKU guidance](https://help.shopify.com/en/manual/products/details/sku)
   * [What is a SKU - and how does it help ecommerce sellers?](https://sell.amazon.com/es/blog/sku-definition-guide)

### 4.5. The name of the category constraints
* Use [UTF-8 encoding](https://en.wikipedia.org/wiki/UTF-8) capable of representing all Unicode characters
* String 255 chars (`VARCHAR(255)`)
* Must be present (`NOT NULL` constraint in DB) and not empty (enforce `min_length=1` in Pydantic)
* Must be unique per same parent (composite unique constraint on `(parent_id, name)`)
* References:
   * [Shopify Product Category](https://shopify.dev/docs/api/admin-graphql/latest/objects/ProductCategory)
   * [Magento categories query](https://developer.adobe.com/commerce/webapi/graphql/schema/products/queries/categories/)

### 4.6. The parent field of the category

### 4.7. Pagination of the returned results

### 4.8. Databse to store products, categories and images

### 4.9. Unit test for real database or for mock database
