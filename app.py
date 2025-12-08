import streamlit as st
import pandas as pd
import tempfile
import os
import main
import yaml

st.title("Augment Your Team's QA Analysis")
# Upload audio file
audio_files = st.file_uploader("Upload audio file (.wav)", type=["wav"],accept_multiple_files=True)

# Upload YAML file
yaml_file = st.file_uploader("Upload Questions file for Analysis (.yaml)", type=["yaml", "yml"])
user_email = st.text_input("Enter your work email to receive your scores:")



def audio_to_scored_df(f_list,qa_prompt_templates ):
    for f in f_list:
        print( 'starting with file index'  , f_list.index(f))
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_audio:
            tmp_audio.write(f.read())
            tmp_audio_path = tmp_audio.name
        full_transcript=main.transcribe_audio(file_=tmp_audio_path,WHISPER_MODEL_SIZE="base")
        diarized_transcript= main.diarize_transcript(transcript_text=full_transcript)
        df = main.accumalate_scores(prompt_templates=qa_prompt_templates,diarized_transcript=diarized_transcript)
        df['filename_path'] = f.name  # added filename to df to identify each file. 
        print(f.name)
        os.remove(tmp_audio_path)
        
        yield df



# Process button without
# if st.button("Run Scores") and audio_files and yaml_file and user_email:
    

#     with tempfile.NamedTemporaryFile(delete=False, suffix=".yaml") as tmp_yaml:
#         tmp_yaml.write(yaml_file.read())
#         tmp_yaml_path = tmp_yaml.name
#     try:

#         with open(tmp_yaml_path, 'r') as file:
#             qa_prompt_templates = yaml.safe_load(file)
        
#         combined_df = pd.concat(audio_to_scored_df(audio_files,qa_prompt_templates), ignore_index=True)

        
                                
      

#         # Show result
#         st.write("Here is what the results are looking like:")
#         st.dataframe(combined_df)

#         # Provide download link
#         csv = combined_df.to_csv(index=False)
        
#         main.send_csv_via_email(user_email , csv)
        
#         st.success("CSV emailed to " + user_email)
       
#         st.download_button(
#             label="Download CSV",
#             data=csv,
#             file_name="results.csv",
#             mime="text/csv"
#         )
#     finally:
        
#         os.remove(tmp_yaml_path)



# Process button
if st.button("Run Scores") and audio_files and yaml_file and user_email:
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".yaml") as tmp_yaml:
        tmp_yaml.write(yaml_file.read())
        tmp_yaml_path = tmp_yaml.name
    
    try:
        with open(tmp_yaml_path, 'r') as file:
            qa_prompt_templates = yaml.safe_load(file)
        
        combined_df = pd.concat(audio_to_scored_df(audio_files,qa_prompt_templates), ignore_index=True)

        # Show result
        st.write("Here is a view of your results:")
        st.dataframe(combined_df)

        # Provide download link
        csv = combined_df.to_csv(index=False)
        
        # Get email credentials from Streamlit secrets
        try:
            sender_email = st.secrets["email"]["sender_email"]
            sender_password = st.secrets["email"]["sender_password"]
            
            main.send_csv_via_email(
                receiver_email=user_email,
                csv_content=csv,
                sender_email=sender_email,
                sender_password=sender_password
            )
            
            st.success(f" CSV emailed to {user_email}")
            
        except KeyError:
            st.error(
                "! Email credentials not configured. Please set up your .streamlit/secrets.toml file. "
                "You can still download the CSV below."
            )
        except ValueError as e:
            st.error(f"! Email error: {str(e)}")
        except Exception as e:
            st.error(f"! Failed to send email: {str(e)}")
       
        st.download_button(
            label="Download CSV",
            data=csv,
            file_name="results.csv",
            mime="text/csv"
        )
        
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
    finally:
        os.remove(tmp_yaml_path)