# Implementation Plan: Intelligent Orchestration Agent

## Overview

This implementation plan creates an end-to-end intelligent notification orchestration pipeline that leverages LLM capabilities for automated template selection and channel priority determination. The system extends the existing BedrockLLMService and OrchestrationAgent to provide a complete flow from user input to multi-channel delivery with intelligent decision-making at each step.

## Tasks

- [x] 1. Extend BedrockLLMService with template selection and priority determination methods
  - [x] 1.1 Add select_template method to BedrockLLMService
    - Implement async method that accepts message_content, tenant_id, and list of available templates
    - Build LLM prompt that analyzes content characteristics and template metadata
    - Parse LLM response to extract template_id, confidence_score, and reasoning
    - Add fallback logic for rule-based template matching when LLM fails
    - _Requirements: 2.1, 2.2, 2.3, 2.6, 2.7_
  
  - [ ]* 1.2 Write unit tests for select_template method
    - Test successful template selection with valid inputs
    - Test fallback behavior when LLM service fails
    - Test handling of empty template list
    - Test confidence score validation
    - _Requirements: 2.1, 2.2, 2.7_
  
  - [x] 1.3 Add determine_channel_priority method to BedrockLLMService
    - Implement async method that accepts message_content, urgency, user_context, template_info, and provider_health
    - Build LLM prompt incorporating urgency analysis, user preferences, engagement history, and provider status
    - Parse LLM response to extract ordered channel list with timing recommendations
    - Implement critical priority override logic (SMS/push first regardless of preferences)
    - Add quiet hours handling for non-urgent notifications
    - Add fallback to existing fallback_routing logic when LLM fails
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9_
  
  - [ ]* 1.4 Write unit tests for determine_channel_priority method
    - Test priority determination with various urgency levels
    - Test critical priority override behavior
    - Test quiet hours scheduling logic
    - Test fallback behavior when LLM fails
    - _Requirements: 4.1, 4.7, 4.8, 4.9_

- [x] 2. Create IntelligentOrchestrationAgent service
  - [x] 2.1 Create intelligent_orchestration_agent.py in src/services/
    - Create IntelligentOrchestrationAgent class with __init__ accepting database connection and service dependencies
    - Inject BedrockLLMService, TemplateEngine, ProviderManager, NotificationService, and DeduplicationService
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.7_
  
  - [x] 2.2 Implement orchestrate_send method - input validation and template selection
    - Accept message_content, tenant_id, user_id, and optional metadata (idempotency_key, custom_variables)
    - Validate message_content length (max 10000 characters)
    - Validate required parameters and return descriptive errors
    - Fetch all active templates for tenant from database
    - Call BedrockLLMService.select_template to get best template
    - Log template selection with reasoning
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 7.2_
  
  - [x] 2.3 Implement orchestrate_send method - user context fetching
    - Fetch user preferences from UserPreference table
    - Fetch user engagement statistics (success rates per channel)
    - Include timezone and quiet_hours in context
    - Include preferred_channels ranking
    - Use system defaults when user preferences don't exist
    - Fetch provider health status using ProviderManager
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 9.3_
  
  - [x] 2.4 Implement orchestrate_send method - priority determination and template rendering
    - Call BedrockLLMService.analyze_content_urgency to determine urgency level
    - Call BedrockLLMService.determine_channel_priority with full context
    - Log priority determination with reasoning
    - Merge message_content variables with user_context variables
    - Use TemplateEngine to render selected template
    - Handle missing template variables with empty string fallbacks
    - Validate rendered content against channel-specific length limits
    - Fall back to raw message_content if rendering fails
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.1, 5.2, 5.3, 5.4, 5.5, 9.2_
  
  - [x] 2.5 Implement orchestrate_send method - notification pipeline execution
    - Iterate through channels in determined priority order
    - Use NotificationService for each channel delivery attempt
    - Stop attempting remaining channels on first successful delivery
    - Continue to next channel on delivery failure
    - Respect timing recommendations (immediate vs scheduled)
    - Update user engagement statistics after each attempt
    - Use DeduplicationService to prevent duplicate sends
    - Log all delivery attempts with results
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 9.4, 9.5_
  
  - [x] 2.6 Implement orchestrate_send method - response and error handling
    - Build response containing selected_template, priority_order, delivery_status, and reasoning
    - Include LLM reasoning for transparency
    - Include error details and fallback actions when errors occur
    - Record processing time for performance monitoring
    - Implement retry logic for database failures (retry once)
    - Queue notification for retry when all channels fail
    - Ensure no unhandled exceptions propagate to caller
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 8.1, 8.2, 8.3, 8.4, 8.5_
  
  - [ ]* 2.7 Write integration tests for IntelligentOrchestrationAgent
    - Test complete orchestration flow with successful delivery
    - Test fallback behavior when LLM services fail
    - Test multi-channel fallback when first channel fails
    - Test quiet hours scheduling
    - Test deduplication prevention
    - _Requirements: 1.1, 2.1, 4.1, 6.1, 6.8_

- [ ] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Create API endpoint for orchestration
  - [x] 4.1 Create orchestration.py router in src/api/routers/
    - Create FastAPI router with prefix /api/v1/orchestrate
    - Add authentication and tenant authorization dependencies
    - _Requirements: 10.1, 10.3_
  
  - [x] 4.2 Define request and response schemas in src/api/schemas.py
    - Create OrchestrationRequest schema with message_content, tenant_id, user_id, and optional metadata fields
    - Create OrchestrationResponse schema with selected_template, priority_order, delivery_status, reasoning, and processing_time
    - Add validation for message_content max length (10000 chars)
    - _Requirements: 10.2, 10.4, 10.5_
  
  - [x] 4.3 Implement POST /api/v1/orchestrate/send endpoint
    - Accept OrchestrationRequest JSON payload
    - Validate authentication and tenant authorization
    - Instantiate IntelligentOrchestrationAgent with dependencies
    - Call orchestrate_send method
    - Return HTTP 200 with OrchestrationResponse on success
    - Return HTTP 400 for validation errors with descriptive messages
    - Return HTTP 500 for system errors with error tracking IDs
    - Add error logging with tracking IDs
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_
  
  - [x] 4.4 Register orchestration router in src/api/__init__.py or src/main.py
    - Import and include orchestration router in FastAPI app
    - _Requirements: 10.1_
  
  - [ ]* 4.5 Write API endpoint tests
    - Test successful orchestration request
    - Test authentication failure
    - Test validation errors (missing fields, content too long)
    - Test system error handling
    - _Requirements: 10.3, 10.4, 10.5, 10.6_

- [x] 5. Create UI for intelligent orchestration
  - [x] 5.1 Add orchestration section to tenant dashboard HTML
    - Add section to existing tenant dashboard template (src/api/routers/dashboard.html or tenant_portal.py template)
    - Create textarea for message content input (placeholder: "Enter your message content...")
    - Add "Run Pipeline" button with onclick handler
    - Add visual pipeline progress container with stages: analyzing → selecting template → determining priority → sending
    - Add results display container for showing delivery status and reasoning
    - _Requirements: User's key implementation points_
  
  - [x] 5.2 Implement frontend JavaScript for orchestration UI
    - Add event handler for "Run Pipeline" button click
    - Validate message content is not empty before submission
    - Show pipeline progress stages with visual indicators (loading spinners, checkmarks)
    - Make POST request to /api/v1/orchestrate/send with message content and tenant/user IDs
    - Update progress stages as pipeline executes (use polling or websockets if async)
    - Display results including selected template, channel priority order, delivery status, and LLM reasoning
    - Handle and display error messages
    - Add "Clear" or "Reset" button to start new orchestration
    - _Requirements: User's key implementation points_
  
  - [ ]* 5.3 Add CSS styling for orchestration UI
    - Style textarea, button, progress indicators, and results display
    - Add responsive design for mobile devices
    - Add loading animations for progress stages
    - _Requirements: User's key implementation points_

- [ ] 6. Final checkpoint - Integration testing and validation
  - Test complete end-to-end flow from UI to delivery
  - Verify LLM reasoning is displayed correctly
  - Test error handling and fallback scenarios
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- The implementation leverages existing services (BedrockLLMService, TemplateEngine, ProviderManager, NotificationService, DeduplicationService) for seamless integration
- LLM methods use async/await pattern consistent with existing BedrockLLMService
- Error handling includes fallback to rule-based logic when LLM services fail
- The UI integrates into the existing tenant dashboard for unified user experience
- Pipeline progress visualization provides transparency into the orchestration process
