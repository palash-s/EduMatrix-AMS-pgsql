package com.eduMatrix.ams.data.models

/**
 * Represents the different user roles in the system.
 * Each role has different access levels and features.
 */
enum class UserRole {
    ADMIN,
    STAFF,
    STUDENT,
    PARENT;

    companion object {
        fun fromString(role: String): UserRole {
            return when (role.lowercase()) {
                "admin" -> ADMIN
                "staff" -> STAFF
                "student" -> STUDENT
                "parent" -> PARENT
                else -> STUDENT // Default fallback
            }
        }
    }
}

/**
 * Staff-specific roles that provide additional features
 */
data class StaffRoles(
    val isClassTeacher: Boolean = false,
    val isHod: Boolean = false,
    val isEventCoordinator: Boolean = false,
    val isAmcMember: Boolean = false,
    val isAmcHead: Boolean = false,
    val isMentor: Boolean = false
)

/**
 * Core user data returned from login
 */
data class User(
    val userId: String,  // UUID from backend
    val email: String,
    val name: String,
    val role: UserRole,
    val staffRoles: StaffRoles? = null, // Only for staff users
    val departmentId: Int? = null,
    val departmentName: String? = null,
    val mustChangePassword: Boolean = false
)

/**
 * Login response from the API
 */
data class LoginResponse(
    val accessToken: String,
    val refreshToken: String,
    val user: User
)

/**
 * Authentication state for the app
 */
sealed class AuthState {
    object Loading : AuthState()
    object Unauthenticated : AuthState()
    data class Authenticated(val user: User) : AuthState()
    data class Error(val message: String) : AuthState()
    object MustChangePassword : AuthState()
}
