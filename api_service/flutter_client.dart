import 'dart:convert';

// Note: This is a reference implementation.
// In your actual Flutter app, you would use:
// import 'package:flutter/foundation.dart';
// import 'package:http/http.dart' as http;

// Simple HTTP client for reference purposes
class Response {
  final int statusCode;
  final String body;

  Response(this.statusCode, this.body);
}

// Simple HTTP methods for reference purposes
class http {
  static Future<Response> get(Uri url, {Map<String, String>? headers}) async {
    // This is a placeholder. In a real implementation, you would use the http package.
    return Future.value(Response(200, '{}'));
  }

  static Future<Response> post(Uri url, {Map<String, String>? headers, dynamic body}) async {
    // This is a placeholder. In a real implementation, you would use the http package.
    return Future.value(Response(200, '{}'));
  }

  static Future<Response> put(Uri url, {Map<String, String>? headers, dynamic body}) async {
    // This is a placeholder. In a real implementation, you would use the http package.
    return Future.value(Response(200, '{}'));
  }

  static Future<Response> delete(Uri url, {Map<String, String>? headers}) async {
    // This is a placeholder. In a real implementation, you would use the http package.
    return Future.value(Response(200, '{}'));
  }
}

/// API client for the unified API service
class ApiClient {
  final String apiUrl;
  String? _token;

  ApiClient({required this.apiUrl, String? token}) : _token = token;

  /// Set the Discord token for authentication
  void setToken(String token) {
    _token = token;
  }

  /// Get the authorization header for API requests
  String? getAuthHeader() {
    if (_token == null) return null;
    return 'Bearer $_token';
  }

  /// Check if the client is authenticated
  bool get isAuthenticated => _token != null;

  /// Make a request to the API
  Future<dynamic> _makeRequest(String method, String endpoint, {Map<String, dynamic>? data}) async {
    if (_token == null) {
      throw Exception('No token set for API client');
    }

    final headers = {'Authorization': 'Bearer $_token', 'Content-Type': 'application/json'};

    final url = Uri.parse('$apiUrl/$endpoint');
    Response response;

    try {
      if (method == 'GET') {
        response = await http.get(url, headers: headers);
      } else if (method == 'POST') {
        response = await http.post(url, headers: headers, body: data != null ? jsonEncode(data) : null);
      } else if (method == 'PUT') {
        response = await http.put(url, headers: headers, body: data != null ? jsonEncode(data) : null);
      } else if (method == 'DELETE') {
        response = await http.delete(url, headers: headers);
      } else {
        throw Exception('Unsupported HTTP method: $method');
      }

      if (response.statusCode != 200 && response.statusCode != 201) {
        throw Exception('API request failed: ${response.statusCode} - ${response.body}');
      }

      return jsonDecode(response.body);
    } catch (e) {
      print('Error making API request: $e');
      rethrow;
    }
  }

  // ============= Conversation Methods =============

  /// Get all conversations for the authenticated user
  Future<List<Map<String, dynamic>>> getConversations() async {
    final response = await _makeRequest('GET', 'conversations');
    return List<Map<String, dynamic>>.from(response['conversations']);
  }

  /// Get a specific conversation
  Future<Map<String, dynamic>> getConversation(String conversationId) async {
    final response = await _makeRequest('GET', 'conversations/$conversationId');
    return Map<String, dynamic>.from(response);
  }

  /// Create a new conversation
  Future<Map<String, dynamic>> createConversation(Map<String, dynamic> conversation) async {
    final response = await _makeRequest('POST', 'conversations', data: {'conversation': conversation});
    return Map<String, dynamic>.from(response);
  }

  /// Update an existing conversation
  Future<Map<String, dynamic>> updateConversation(Map<String, dynamic> conversation) async {
    final conversationId = conversation['id'];
    final response = await _makeRequest('PUT', 'conversations/$conversationId', data: {'conversation': conversation});
    return Map<String, dynamic>.from(response);
  }

  /// Delete a conversation
  Future<bool> deleteConversation(String conversationId) async {
    final response = await _makeRequest('DELETE', 'conversations/$conversationId');
    return response['success'] as bool;
  }

  // ============= Settings Methods =============

  /// Get settings for the authenticated user
  Future<Map<String, dynamic>> getSettings() async {
    final response = await _makeRequest('GET', 'settings');
    return Map<String, dynamic>.from(response['settings']);
  }

  /// Update settings for the authenticated user
  Future<Map<String, dynamic>> updateSettings(Map<String, dynamic> settings) async {
    final response = await _makeRequest('PUT', 'settings', data: {'settings': settings});
    return Map<String, dynamic>.from(response);
  }
}
