/*
 * Copyright 2025 ATP Project Contributors
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package com.atp.sdk;

import com.atp.sdk.auth.AuthManager;
import com.atp.sdk.config.ATPConfig;
import com.atp.sdk.exception.*;
import com.atp.sdk.model.*;
import com.atp.sdk.streaming.StreamingClient;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import okhttp3.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.io.IOException;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

/**
 * Main ATP client for synchronous and asynchronous operations.
 * 
 * This client provides a comprehensive interface for interacting with the ATP platform,
 * including chat completions, model management, cost tracking, and streaming responses.
 * 
 * Example usage:
 * <pre>
 * ATPClient client = ATPClient.builder()
 *     .apiKey("your-api-key")
 *     .baseUrl("https://api.atp.company.com")
 *     .build();
 * 
 * ChatRequest request = ChatRequest.builder()
 *     .addMessage(ChatMessage.user("Hello, world!"))
 *     .build();
 * 
 * ChatResponse response = client.chatCompletion(request);
 * System.out.println(response.getChoices().get(0).getMessage().getContent());
 * </pre>
 */
public class ATPClient implements AutoCloseable {
    
    private static final Logger logger = LoggerFactory.getLogger(ATPClient.class);
    
    private final ATPConfig config;
    private final AuthManager authManager;
    private final OkHttpClient httpClient;
    private final ObjectMapper objectMapper;
    private final StreamingClient streamingClient;
    
    /**
     * Creates a new ATP client with the specified configuration.
     * 
     * @param config The client configuration
     */
    public ATPClient(ATPConfig config) {
        this.config = config;
        this.authManager = new AuthManager(config);
        this.objectMapper = createObjectMapper();
        this.httpClient = createHttpClient();
        this.streamingClient = new StreamingClient(config, authManager, objectMapper);
    }
    
    /**
     * Creates a builder for configuring the ATP client.
     * 
     * @return A new client builder
     */
    public static Builder builder() {
        return new Builder();
    }
    
    /**
     * Creates a chat completion synchronously.
     * 
     * @param request The chat completion request
     * @return The chat completion response
     * @throws ATPException If the request fails
     */
    public ChatResponse chatCompletion(ChatRequest request) throws ATPException {
        if (request.isStream()) {
            throw new IllegalArgumentException("Use streamChatCompletion() for streaming requests");
        }
        
        try {
            String json = objectMapper.writeValueAsString(request);
            RequestBody body = RequestBody.create(json, MediaType.get("application/json"));
            
            Request httpRequest = new Request.Builder()
                    .url(config.getBaseUrl() + "/v1/chat/completions")
                    .post(body)
                    .headers(Headers.of(getHeaders()))
                    .build();
            
            try (Response response = httpClient.newCall(httpRequest).execute()) {
                return handleResponse(response, ChatResponse.class);
            }
        } catch (IOException e) {
            throw new ATPException("Request failed", e);
        }
    }
    
    /**
     * Creates a chat completion asynchronously.
     * 
     * @param request The chat completion request
     * @return A CompletableFuture containing the chat completion response
     */
    public CompletableFuture<ChatResponse> chatCompletionAsync(ChatRequest request) {
        if (request.isStream()) {
            return CompletableFuture.failedFuture(
                new IllegalArgumentException("Use streamChatCompletion() for streaming requests"));
        }
        
        CompletableFuture<ChatResponse> future = new CompletableFuture<>();
        
        try {
            String json = objectMapper.writeValueAsString(request);
            RequestBody body = RequestBody.create(json, MediaType.get("application/json"));
            
            Request httpRequest = new Request.Builder()
                    .url(config.getBaseUrl() + "/v1/chat/completions")
                    .post(body)
                    .headers(Headers.of(getHeaders()))
                    .build();
            
            httpClient.newCall(httpRequest).enqueue(new Callback() {
                @Override
                public void onFailure(Call call, IOException e) {
                    future.completeExceptionally(new ATPException("Request failed", e));
                }
                
                @Override
                public void onResponse(Call call, Response response) throws IOException {
                    try {
                        ChatResponse chatResponse = handleResponse(response, ChatResponse.class);
                        future.complete(chatResponse);
                    } catch (ATPException e) {
                        future.completeExceptionally(e);
                    } finally {
                        response.close();
                    }
                }
            });
        } catch (Exception e) {
            future.completeExceptionally(new ATPException("Request preparation failed", e));
        }
        
        return future;
    }
    
    /**
     * Creates a streaming chat completion.
     * 
     * @param request The chat completion request (stream will be set to true)
     * @return A Flux of streaming responses
     */
    public Flux<StreamingResponse> streamChatCompletion(ChatRequest request) {
        ChatRequest streamingRequest = request.toBuilder().stream(true).build();
        return streamingClient.streamChatCompletion(streamingRequest);
    }
    
    /**
     * Lists available models.
     * 
     * @return List of available models
     * @throws ATPException If the request fails
     */
    public List<ModelInfo> listModels() throws ATPException {
        Request request = new Request.Builder()
                .url(config.getBaseUrl() + "/v1/models")
                .get()
                .headers(Headers.of(getHeaders()))
                .build();
        
        try (Response response = httpClient.newCall(request).execute()) {
            ModelsResponse modelsResponse = handleResponse(response, ModelsResponse.class);
            return modelsResponse.getModels();
        } catch (IOException e) {
            throw new ATPException("Request failed", e);
        }
    }
    
    /**
     * Gets detailed information about a specific model.
     * 
     * @param modelId The model identifier
     * @return Detailed model information
     * @throws ATPException If the request fails
     */
    public ModelInfo getModelInfo(String modelId) throws ATPException {
        Request request = new Request.Builder()
                .url(config.getBaseUrl() + "/v1/models/" + modelId)
                .get()
                .headers(Headers.of(getHeaders()))
                .build();
        
        try (Response response = httpClient.newCall(request).execute()) {
            return handleResponse(response, ModelInfo.class);
        } catch (IOException e) {
            throw new ATPException("Request failed", e);
        }
    }
    
    /**
     * Lists available providers.
     * 
     * @return List of available providers
     * @throws ATPException If the request fails
     */
    public List<ProviderInfo> listProviders() throws ATPException {
        Request request = new Request.Builder()
                .url(config.getBaseUrl() + "/v1/providers")
                .get()
                .headers(Headers.of(getHeaders()))
                .build();
        
        try (Response response = httpClient.newCall(request).execute()) {
            ProvidersResponse providersResponse = handleResponse(response, ProvidersResponse.class);
            return providersResponse.getProviders();
        } catch (IOException e) {
            throw new ATPException("Request failed", e);
        }
    }
    
    /**
     * Gets cost information for the current tenant/project.
     * 
     * @param startDate Start date for cost query (ISO format, optional)
     * @param endDate End date for cost query (ISO format, optional)
     * @return Cost information and breakdown
     * @throws ATPException If the request fails
     */
    public CostInfo getCostInfo(String startDate, String endDate) throws ATPException {
        HttpUrl.Builder urlBuilder = HttpUrl.parse(config.getBaseUrl() + "/v1/cost").newBuilder();
        
        if (startDate != null) {
            urlBuilder.addQueryParameter("start_date", startDate);
        }
        if (endDate != null) {
            urlBuilder.addQueryParameter("end_date", endDate);
        }
        
        Request request = new Request.Builder()
                .url(urlBuilder.build())
                .get()
                .headers(Headers.of(getHeaders()))
                .build();
        
        try (Response response = httpClient.newCall(request).execute()) {
            return handleResponse(response, CostInfo.class);
        } catch (IOException e) {
            throw new ATPException("Request failed", e);
        }
    }
    
    /**
     * Gets usage statistics.
     * 
     * @param startDate Start date for usage query (ISO format, optional)
     * @param endDate End date for usage query (ISO format, optional)
     * @return Usage statistics and metrics
     * @throws ATPException If the request fails
     */
    public UsageStats getUsageStats(String startDate, String endDate) throws ATPException {
        HttpUrl.Builder urlBuilder = HttpUrl.parse(config.getBaseUrl() + "/v1/usage").newBuilder();
        
        if (startDate != null) {
            urlBuilder.addQueryParameter("start_date", startDate);
        }
        if (endDate != null) {
            urlBuilder.addQueryParameter("end_date", endDate);
        }
        
        Request request = new Request.Builder()
                .url(urlBuilder.build())
                .get()
                .headers(Headers.of(getHeaders()))
                .build();
        
        try (Response response = httpClient.newCall(request).execute()) {
            return handleResponse(response, UsageStats.class);
        } catch (IOException e) {
            throw new ATPException("Request failed", e);
        }
    }
    
    /**
     * Checks the health of the ATP service.
     * 
     * @return Health status information
     * @throws ATPException If the request fails
     */
    public Map<String, Object> healthCheck() throws ATPException {
        Request request = new Request.Builder()
                .url(config.getBaseUrl() + "/health")
                .get()
                .headers(Headers.of(getHeaders()))
                .build();
        
        try (Response response = httpClient.newCall(request).execute()) {
            return handleResponse(response, new TypeReference<Map<String, Object>>() {});
        } catch (IOException e) {
            throw new ATPException("Request failed", e);
        }
    }
    
    /**
     * Gets the client configuration.
     * 
     * @return The client configuration
     */
    public ATPConfig getConfig() {
        return config;
    }
    
    @Override
    public void close() {
        if (httpClient != null) {
            httpClient.dispatcher().executorService().shutdown();
            httpClient.connectionPool().evictAll();
        }
    }
    
    private OkHttpClient createHttpClient() {
        OkHttpClient.Builder builder = new OkHttpClient.Builder()
                .connectTimeout(Duration.ofSeconds(config.getConnectTimeout()))
                .readTimeout(Duration.ofSeconds(config.getReadTimeout()))
                .writeTimeout(Duration.ofSeconds(config.getWriteTimeout()));
        
        // Add retry interceptor
        if (config.getMaxRetries() > 0) {
            builder.addInterceptor(new RetryInterceptor(config.getMaxRetries()));
        }
        
        // Add logging interceptor if enabled
        if (config.isLogRequests()) {
            HttpLoggingInterceptor loggingInterceptor = new HttpLoggingInterceptor(logger::debug);
            loggingInterceptor.setLevel(HttpLoggingInterceptor.Level.BODY);
            builder.addInterceptor(loggingInterceptor);
        }
        
        return builder.build();
    }
    
    private ObjectMapper createObjectMapper() {
        return ObjectMapperFactory.create();
    }
    
    private Map<String, String> getHeaders() {
        Map<String, String> headers = authManager.getAuthHeaders();
        
        headers.put("User-Agent", "ATP-Java-SDK/" + getClass().getPackage().getImplementationVersion());
        headers.put("Content-Type", "application/json");
        headers.put("Accept", "application/json");
        
        if (config.getTenantId() != null) {
            headers.put("X-ATP-Tenant-ID", config.getTenantId());
        }
        
        if (config.getProjectId() != null) {
            headers.put("X-ATP-Project-ID", config.getProjectId());
        }
        
        return headers;
    }
    
    private <T> T handleResponse(Response response, Class<T> responseType) throws ATPException, IOException {
        return handleResponse(response, objectMapper.getTypeFactory().constructType(responseType));
    }
    
    private <T> T handleResponse(Response response, TypeReference<T> typeReference) throws ATPException, IOException {
        return handleResponse(response, objectMapper.getTypeFactory().constructType(typeReference));
    }
    
    private <T> T handleResponse(Response response, com.fasterxml.jackson.databind.JavaType javaType) throws ATPException, IOException {
        if (!response.isSuccessful()) {
            handleErrorResponse(response);
        }
        
        ResponseBody body = response.body();
        if (body == null) {
            throw new ATPException("Empty response body");
        }
        
        String responseText = body.string();
        return objectMapper.readValue(responseText, javaType);
    }
    
    private void handleErrorResponse(Response response) throws ATPException, IOException {
        int statusCode = response.code();
        String errorMessage = "Request failed with status: " + statusCode;
        
        ResponseBody body = response.body();
        Map<String, Object> errorDetails = null;
        
        if (body != null) {
            try {
                String errorText = body.string();
                errorDetails = objectMapper.readValue(errorText, new TypeReference<Map<String, Object>>() {});
                errorMessage = errorDetails.getOrDefault("message", errorMessage).toString();
            } catch (Exception e) {
                logger.warn("Failed to parse error response", e);
            }
        }
        
        switch (statusCode) {
            case 401:
                throw new AuthenticationException("Invalid API key or expired token");
            case 403:
                throw new AuthorizationException("Insufficient permissions");
            case 404:
                throw new ModelNotFoundException("Requested model not found");
            case 402:
                throw new InsufficientCreditsException("Insufficient credits");
            case 429:
                String retryAfter = response.header("Retry-After");
                throw new RateLimitException("Rate limit exceeded", retryAfter != null ? Integer.parseInt(retryAfter) : null);
            case 422:
                throw new ValidationException("Request validation failed", errorDetails);
            case 500:
            case 502:
            case 503:
            case 504:
                throw new ServerException("Server error: " + statusCode, statusCode);
            default:
                throw new ATPException(errorMessage, errorDetails);
        }
    }
    
    /**
     * Builder class for creating ATP clients.
     */
    public static class Builder {
        private final ATPConfig.Builder configBuilder = ATPConfig.builder();
        
        public Builder apiKey(String apiKey) {
            configBuilder.apiKey(apiKey);
            return this;
        }
        
        public Builder baseUrl(String baseUrl) {
            configBuilder.baseUrl(baseUrl);
            return this;
        }
        
        public Builder tenantId(String tenantId) {
            configBuilder.tenantId(tenantId);
            return this;
        }
        
        public Builder projectId(String projectId) {
            configBuilder.projectId(projectId);
            return this;
        }
        
        public Builder timeout(Duration timeout) {
            configBuilder.connectTimeout((int) timeout.getSeconds())
                         .readTimeout((int) timeout.getSeconds())
                         .writeTimeout((int) timeout.getSeconds());
            return this;
        }
        
        public Builder maxRetries(int maxRetries) {
            configBuilder.maxRetries(maxRetries);
            return this;
        }
        
        public Builder logRequests(boolean logRequests) {
            configBuilder.logRequests(logRequests);
            return this;
        }
        
        public Builder config(ATPConfig config) {
            return new Builder().fromConfig(config);
        }
        
        private Builder fromConfig(ATPConfig config) {
            configBuilder.apiKey(config.getApiKey())
                         .baseUrl(config.getBaseUrl())
                         .tenantId(config.getTenantId())
                         .projectId(config.getProjectId())
                         .connectTimeout(config.getConnectTimeout())
                         .readTimeout(config.getReadTimeout())
                         .writeTimeout(config.getWriteTimeout())
                         .maxRetries(config.getMaxRetries())
                         .logRequests(config.isLogRequests());
            return this;
        }
        
        public ATPClient build() {
            return new ATPClient(configBuilder.build());
        }
    }
}