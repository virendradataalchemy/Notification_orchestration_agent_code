-- Add call recording fields to communications table
-- Run this in your Supabase SQL editor

-- Add recording URL field
ALTER TABLE communications 
ADD COLUMN IF NOT EXISTS recording_url TEXT,
ADD COLUMN IF NOT EXISTS recording_duration INTEGER,
ADD COLUMN IF NOT EXISTS recording_sid TEXT;

-- Add index for faster lookups
CREATE INDEX IF NOT EXISTS idx_communications_recording_sid ON communications(recording_sid);

-- Add comment
COMMENT ON COLUMN communications.recording_url IS 'URL to the call recording (for voice channel)';
COMMENT ON COLUMN communications.recording_duration IS 'Duration of the recording in seconds';
COMMENT ON COLUMN communications.recording_sid IS 'Twilio recording SID';
