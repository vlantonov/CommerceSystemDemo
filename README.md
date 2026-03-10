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

### 4.2. Constraints to text fields according to the established practices in existing systems

### 4.3. The format and the storage of the image is to be chosen following the established practices in existing systems

### 4.4. The format unique product identifier (SKU) is to be chosen following the established practices in existing systems

### 4.5. The name of the category constraints

### 4.6. The parent field of the category

### 4.7. Pagination of the returned results

### 4.8. Databse to store products, categories and images

### 4.9. Unit test for real database or for mock database
