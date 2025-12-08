import pandas as pd
import datetime as dt
from faster_whisper import WhisperModel
from datetime import timedelta
import openai
import requests
import json
import polars as pl
import yaml
from collections import Counter
import yamllint
import smtplib
from email.message import EmailMessage


def transcribe_audio(file_,WHISPER_MODEL_SIZE):
    tstrt= dt.datetime.now()
    print("Loading Whisper model")
    model = WhisperModel(WHISPER_MODEL_SIZE, compute_type="int8")
    print(f"Transcribing '{file_}'.")
    segments, info = model.transcribe(file_, beam_size=5, vad_filter=True)
    # Merge all segment texts into one full transcript
    full_transcript = " ".join([segment.text for segment in segments])
    tend= dt.datetime.now()
    print(' This operation took ',    ( tend-tstrt).total_seconds())
    return full_transcript


def generate_ollama_response(my_prompt):
    tstrt= dt.datetime.now()
    ollama_api_url = "http://localhost:11434/api/generate" # local: do not need to change unless specifically running the model elsewhere
    #ollama_api_url = ollama_api_url = "http://34.171.207.197:11434/api/generate"
    ollama_model = "mistral" # this contains many options for models https://ollama.com/search. Mistral is recommended for quality and weight

    response = requests.post(
    ollama_api_url,
    json={
        "model": ollama_model,
        "prompt": my_prompt,
        "stream": False,
        "temperature" : 0,
         "seed" : 313
    
    })
    if response.ok:
        print("\n" + "="*50)
        print(" Generating Response")
        print("="*50)
        print(response.json()["response"])
    else:
        print("Error communicating with Ollama:")
        print(response.text)
    tend= dt.datetime.now()
    print(' This operation took ',    ( tend-tstrt).total_seconds())
    return response.json()["response"]


def diarize_transcript(transcript_text):
    prompt_diarization = f"""
    This is a transcript of a customer support call at a disaster relief center. The transcript is machine generated using Open AI Whisper Model and may contain small inconsistenices. Your task is to label each dialogue as 
    either "Agent:" or "Caller:" based on the content and tone. The conversation is typically started off by the agent. The agent starts off the conversation with their introduction and asking the caller's identification. The caller responds by identifying themself and begin to explain the reason for their call.
    As you attempt this diarization task, you are allowed to fix spelling errors and punctuation. You must not add any additional lines or content to the transcript. You must only return the transcript and no additional text in your response. You 
    must not remove any text or lines from the content either. If you are not sure about who said a particular line, you can stop the task and respond only with "Failure 001: Unsure about speaker diarization. Please refer to human."

    TRANSCRIPT:
    {transcript_text}"""
    diarized_transcript= generate_ollama_response(prompt_diarization)
    return diarized_transcript

""" The function score_from_key requires a text transcript, a role for the Mistral model's context, a key from the prompt YAML and n_agents
transcript: A diarized (ideally) string containing a conversation between an agent and a customer. 
role: The role for model's context. Can be system role
config_prompt_key_str = This is a key in the YAML. The YAML file is supposed to contain the attribute 'full_score' and 'question' for a particular key.
n_agents: Like humans, language models can make mistakes. this represents the number of times we want to call the language model to ask for the score. 
Increasing n_agents would improve the correctness of the score however, it would also result in a higher latency.
"""

def score_from_key(transcript,prompt_templates, role,config_prompt_key_str , n_agents):
    configured_max_score=prompt_templates['templates'][config_prompt_key_str]['full_score']
    retrictions= f"""Your final response should only contain the score based on your best judgement. The score can either be 0 OR {configured_max_score}. Do not return a score between 0 and {configured_max_score}. Do not include any additional text or characters. If you do not understand how to score a question, you may stop the scoring and respond only with 'Failure 002: Unsure about question scoring!'."""
    prompt= role + ' Question: ' +  prompt_templates['templates'][config_prompt_key_str]['question'] + ' ' + retrictions 
    #print(prompt)
    final_prompt = prompt + '\n Diarized transcript : \n' + transcript
    #score_string= generate_ollama_response(final_prompt)
    score_string = [generate_ollama_response(final_prompt) for _ in range(n_agents)]
    highest_vote_score = Counter(score_string).most_common(1)[0][0]
    

    return highest_vote_score




def accumalate_scores(prompt_templates,diarized_transcript):
    tstrt = dt.datetime.now()
    results_dict = {}
    system_role=f"""You are an experienced customer service quality assurance analyst. Your job is to score customer and agent interactions. You are given a diarized transcript of a customer and an agent. You are to answer the following questions about the transcript."""
    for key in prompt_templates['templates'].keys():
        print(key)
        try:
            s = score_from_key(transcript=diarized_transcript,prompt_templates=prompt_templates,
                               role=system_role, config_prompt_key_str=key, n_agents=1)
            c_name = prompt_templates['templates'][key]['question_title']  
                # Handle duplicate question_title by summing scores. If the question title is the same, we assume that scores are to be added

            if c_name in results_dict:
                results_dict[c_name] += int(s)
            else:
                results_dict[c_name] = int(s)

        except Exception as e:
            print('Error at ', key, 'Exception',e)
            s=-1000
        
        
        
    df_results = pd.DataFrame([results_dict])

    tend = dt.datetime.now()
    #print('It took', (tend - tstrt).total_seconds(), 'seconds to score this call')
    return df_results
#email function with email credentials from OS env or streamlit secrets
def send_csv_via_email(receiver_email, csv_content, sender_email=None, sender_password=None):
    """
    Send CSV file via email using provided credentials.
    
    Args:
        receiver_email: Recipient's email address
        csv_content: CSV data as string
        sender_email: Sender's email (from Streamlit secrets or env var)
        sender_password: App password (from Streamlit secrets or env var)
    
    Raises:
        ValueError: If credentials are not provided
        smtplib.SMTPException: If email sending fails
    """
    # Try to get credentials from multiple sources
    if sender_email is None:
        sender_email = os.environ.get('SENDER_EMAIL')
    
    if sender_password is None:
        sender_password = os.environ.get('SENDER_PASSWORD')
    
    # Validate credentials are provided
    if not sender_email or not sender_password:
        raise ValueError(
            "Email credentials not found. Please set SENDER_EMAIL and SENDER_PASSWORD "
            "in Streamlit secrets or environment variables."
        )
    
    try:
        msg = EmailMessage()
        msg['Subject'] = "PFA - AI generated scores are attached!"
        msg['From'] = sender_email
        msg['To'] = receiver_email
        msg.set_content("Please find the scored file attached.")
        msg.add_attachment(
            csv_content.encode('utf-8'), 
            maintype='text', 
            subtype='csv', 
            filename='your_scored_file.csv'
        )
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(sender_email, sender_password)
            smtp.send_message(msg)
            
        print(f"Email successfully sent to {receiver_email}")
        
    except smtplib.SMTPAuthenticationError:
        raise ValueError(
            "Email authentication failed. Please check your credentials. "
            "For Gmail, make sure you're using an App Password, not your regular password."
        )
    except smtplib.SMTPException as e:
        raise Exception(f"Failed to send email: {str(e)}")