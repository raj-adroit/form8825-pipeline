Use Case: extract data from 8825 form

AI assistants are expected. Please prepare for a 20-minute solution walkthrough in the in-person interview after you finish your code.


Task 1: Given a sample 8825 tax return file (f8825.pdf), write a Python document processing script to extract all the income and expenses for each property in the 8825 form with open source PDF processing or OCR library free of your choice.

Expected Json output file: 8825_output.json is provided.

What are the possible failures when processing PDF files and how to handle them?

State how your script determines whether a PDF has a usable text layer, what it does when it doesn't, and what you would change to support scanned input in pdf file.
(implementation is optional for scanned pdf, only if you have additional time)


Task 2: Create a new test pdf file with simulated data to test multiple properties in a single 8825 form (new 8825 form test file with A,B,C 3 properties), and its expected JSON, generated from the same source data. Expand the document processing script to support data extraction and validation for multiple properties in 8825 form.


Task 3: Design DB tables, API and create a UI page using REACT to display the result and allow update on the numbers manually from the UI. Extraction results and changes should be tracked in backend db tables. (recommend to use Vite + FastAPI + SQLite or you can make your alternative choices)


Task 4: Create test script to 1) check if the Python document processing script produces the expected json result for each propery in 8825 form 2) validate the extracted total income, total expense and net income (line 2c, 18 and 19) are accurate. 3) Produce a test result file in csv format. (design the test result table on your own) 4) UI test automation

total income Line 2c = 2a + 2b

Total expense Line 18 = all the numbers for expense items adding together

Net income = total income - total expense

Grant total net income = sum of net income for all properties


Evaluation rubric -
  - AI tool proficiency (prompt quality, iteration speed)
  - Code quality (structure, error handling)
  - Accuracy of extraction
  - Data modeling
  - Front-end implementation
  - API design


To complete Task 1-3, normally 2-3 hours by using a coding agent (Claude Code, Copilot, Cursor, etc.)

Task 4 is a bonus task, optional

If you run out of time, note what you'd do next - we grade that too.
