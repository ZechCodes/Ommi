# Welcome to Ommi ORM!

Ommi is an OMM (Object Model Mapper) designed to simplify database interactions by covering the common 80% use case. It provides a consistent and intuitive interface, abstracting away the complexities of underlying database systems and drivers.

**Key Goals of Ommi:**

*   **Simplicity:** Get started quickly without needing deep database expertise.
*   **Consistency:** Use the same API regardless of your chosen database (once a driver is available).
*   **Flexibility:** Works seamlessly with popular data class libraries like Pydantic, attrs, and standard Python dataclasses.

This documentation will guide you through installing Ommi, getting started with its features, and understanding how to leverage its capabilities in your projects.

**Focus on `Ommi`:**

It's important to note that Ommi is built with two levels of abstraction:

*   **Drivers:** These are the lower-level components that communicate directly with specific databases. While essential, they are not the intended primary interface for most users.
*   **`Ommi` Database Type:** This is the higher-level, user-friendly interface that you will typically interact with. All examples and tutorials in this documentation will focus on using the `Ommi` object after it has been initialized with a driver.

Ready to dive in? Head over to the [Getting Started](getting-started.md) guide! 