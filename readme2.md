This project is done with react js and python, to be able to test this project the dependencies have to be downloaded locally. To run this project use the following steps:

### Install prerequisites
- Python: Download and install from python.org.
- Node.js: Download and install from nodejs.org (This allows you to run React).
- npm: Comes bundled with Node.js, but you can also install it separately from npmjs.com.

### Setup the Backend(python)
- Open your terminal/command prompt.
- Navigate to the project folder.
- Install the required libraries for the server: pip install flask flask-cors

### setup Frontend
- open your terminal
- Navigate to your project folder.
- Create the React app: 
npx create-react-app frontend (you can delete the frontend folder presently in the project folder)
- Go into the new folder: cd frontend
- Install Axios (used to talk to Python): npm install axios
- Replace the code: Open frontend/src/App.js in your IDE, delete everything that is in it and replace it with the code found in the file test.js found in the folder frontend_test.

### How to Run (The "Workflow")
- in your project folder open the termonal and navigate to the frontend folder : cd frontend
- In the frontend directory, run : npm start 
- In a different teminal directly in your project folder directory run python server.py to launch network
- This will run the node.py file in the background

### Install gRPC tools
- You need to install these libraries in the project folder terminal: pip install grpcio grpcio-tools


