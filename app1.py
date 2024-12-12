from flask import Flask, request, jsonify
import openai
import os

# Initialize Flask app
app = Flask(__name__)

# Set OpenAI API key
openai.api_key = 'your_openai_api_key'  # Replace with your OpenAI API key

@app.route('/')
def home():
    return 'Welcome to ChatGPT Flask API!'

@app.route('/chat', methods=['POST'])
def chat():
    # Get user input from the request
    user_input = request.json.get('message')

    if not user_input:
        return jsonify({'error': 'No message provided'}), 400

    try:
        # Call OpenAI's GPT API
        response = openai.Completion.create(
            engine="gpt-4",  # You can use "gpt-3.5-turbo" or other models
            prompt=user_input,
            max_tokens=150,
            temperature=0.7
        )
        
        # Get the response text
        gpt_response = response.choices[0].text.strip()

        # Return the response to the user
        return jsonify({'response': gpt_response})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
