package models

import (
	"time"

	"gorm.io/gorm"
)

type Task struct {
	ID          uint           `json:"id" gorm:"primaryKey"`
	Title       string         `json:"title"`
	IsDone      bool           `json:"is_done"`
	StartTime   string         `json:"start_time"` // HH:mm
	EndTime     string         `json:"end_time"`   // HH:mm
	Date        string         `json:"date"`       // YYYY-MM-DD
	CreatedAt   time.Time      `json:"created_at"`
	UpdatedAt   time.Time      `json:"updated_at"`
	DeletedAt   gorm.DeletedAt `json:"deleted_at" gorm:"index"`
}

type Goal struct {
	ID          uint           `json:"id" gorm:"primaryKey"`
	Title       string         `json:"title"`
	Type        string         `json:"type"` // day, month, year
	Date        string         `json:"date,omitempty"` // YYYY-MM-DD for day
	Month       string         `json:"month,omitempty"` // YYYY-MM for month
	Year        string         `json:"year,omitempty"` // YYYY for year
	IsDone      bool           `json:"is_done"`
	CreatedAt   time.Time      `json:"created_at"`
	UpdatedAt   time.Time      `json:"updated_at"`
}
