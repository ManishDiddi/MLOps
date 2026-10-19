import pytest
import numpy as np

from hello_flask import pancakes


# purpose of fixture is to create resources that can be shared across tests

# pytest fixture for connecting to a database
#@pytest.fixture
#def db_connection():
#	# Simulate a database connection
#	connection = "Database connection established"
#	yield connection
#	# Teardown code
#	connection = None
#	print("Database connection closed")

## use the fixture in a test
#def test_db_connection(db_connection):
#	assert db_connection == "Database connection established"


@pytest.fixture
def client():
	return pancakes.test_client() # test_client() is a function provided by Flask to simulate requests to the application without running a server

def test_my_first_flask_function(client):
	response = client.get('/monday') #.get is used to simulate a GET request to the specified endpoint

	assert response.data == b'No!!! It is Monday!'
	assert response.status_code == 200

def test_main_predict_function(client):

	payload1 = { "Gender": "Male", "Married": "Unmarried", "Credit_History": "Cleared Debts", "ApplicantIncome": 50000, "LoanAmount": 500000000 }

	response = client.post('/predict', json=payload1) #.post is used to simulate a POST request to the specified endpoint with a JSON payload

	assert response.status_code == 200
	#assert response.get_json() == {"loan_approval_status": "Loan Approved"} or response.get_json() == {"loan_approval_status": "Loan Rejected"}, "Unexpected response"

	assert response.get_json() == {"loan_approval_status": "Loan Rejected"}, "Unexpected response"

	payload2 = { "Gender": "Male", "Married": "Unmarried", "Credit_History": "Cleared Debts", "ApplicantIncome": 50000, "LoanAmount": 5 }

	response = client.post('/predict', json=payload2) #.post is used to simulate a POST request to the specified endpoint with a JSON payload

	assert response.status_code == 200
	assert response.get_json() == {"loan_approval_status": "Loan Approved"}, "Unexpected response"



def test_predict_function_with_varied_inputs(client):

    for i in range(100):
        if i % 10 == 0:
            print(f"Running iteration {i}/100")
        
        rng_payload = { "Gender":  np.random.choice(["Male", "Female"]),
                            "Married": np.random.choice(["Married", "Unmarried"]),
                            "Credit_History": np.random.choice(["Cleared Debts", "Uncleared Debts"]),
                            "ApplicantIncome": np.random.randint(1000, 100000),
                            "LoanAmount": np.random.randint(1000, 1000000) }
            
        response = client.post('/predict', json=rng_payload)
        assert response.status_code == 200, f"Expected status code 200, got {response.status_code} for payload: {rng_payload}"
        assert response.json in [{"loan_approval_status": "Loan Approved"}, {"loan_approval_status": "Loan Rejected"}], \
            f"Unexpected response for payload: {rng_payload}. Response: {response.json}"
